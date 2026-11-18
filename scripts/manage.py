#!/usr/bin/env python3
"""Install, reinstall, or uninstall LCARS without replacing unrelated shell configuration."""
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ['menu', 'clock', 'workspaces', 'weather', 'keyboard-layout', 'system-update', 'indicators']
# Terminal configs are not shipped: Omarchy renders them from colors.toml.
THEME_FILES = ['colors.toml', 'shell.toml', 'hyprland.lua', 'icons.theme']
# Hooks earlier installs added. Reinstall removes them.
# vscode-terminal copied Foot's swapped slots into VS Code after each theme set.
# foot-opacity kept live Foot alpha in step; transparency is now Omarchy's Glassy toggle.
RETIRED_HOOKS = {'lcars-vscode-terminal.py', 'lcars-vscode-terminal.sh', 'lcars-foot-opacity.py', 'lcars-foot-opacity.sh'}
# Always shipped with the palette so GTK4/libadwaita apps can follow LCARS.
GTK4_HOOK_PY = 'lcars-gtk4-libadwaita.py'
GTK4_HOOK_SH = 'lcars-gtk4.sh'
# Omarchy paints every VS Code surface from one background. This hook
# rewrites the generated theme with a few distinct fills.
VSCODE_HOOK_PY = 'lcars-vscode-surfaces.py'
VSCODE_HOOK_SH = 'lcars-vscode-surfaces.sh'
# Firefox chrome follows GTK system colors, not the libadwaita palette.
FIREFOX_HOOK_PY = 'lcars-firefox-chrome.py'
FIREFOX_HOOK_SH = 'lcars-firefox.sh'
# (installed helper, theme-set wrapper, path inside this repo)
PALETTE_HOOKS = (
    (GTK4_HOOK_PY, GTK4_HOOK_SH, 'scripts/gtk4-libadwaita.py'),
    (VSCODE_HOOK_PY, VSCODE_HOOK_SH, 'scripts/vscode-surfaces.py'),
    (FIREFOX_HOOK_PY, FIREFOX_HOOK_SH, 'scripts/firefox-chrome.py'),
)
PALETTE_HOOK_NAMES = {name for hook in PALETTE_HOOKS for name in hook[:2]}

def write_json(path, data):
    # A symlink to a regular file is a versioned dotfile. Replace that file so
    # the link stays. os.replace on the link itself would remove the link.
    dest = path
    if path.is_symlink():
        dest = Path(os.path.realpath(path))
        if not dest.is_file():
            raise RuntimeError('Refusing to write through symlink: ' + str(path))
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + '.lcars-tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(dest)

def digest(path):
    # Hash a symlink as a link. Never follow it: a wallpaper folder is often
    # linked from the theme, and reading through it would hash the user's pictures.
    if path.is_symlink():
        h = hashlib.sha256()
        h.update(b'link:')
        h.update(os.readlink(path).encode())
        return h.hexdigest()
    if not path.exists():
        return None
    h = hashlib.sha256()
    files = [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_symlink() or p.is_file())
    for file in files:
        rel = file.name if path.is_file() else str(file.relative_to(path))
        h.update(rel.encode())
        if file.is_symlink():
            h.update(b'link:')
            h.update(os.readlink(file).encode())
        else:
            h.update(file.read_bytes())
    return h.hexdigest()

def regular_files_equal(installed, incoming):
    """True when every regular file in installed has the same bytes in incoming.

    Symlinks are ignored and not followed. A file that exists only in installed
    is a local addition. Files that exist only in incoming are updates.
    """
    def files(root):
        if root.is_symlink() or not root.exists():
            return {}
        found = {}
        paths = [root] if root.is_file() else [p for p in root.rglob('*') if p.is_file() and not p.is_symlink()]
        for file in paths:
            rel = '.' if root.is_file() else str(file.relative_to(root))
            found[rel] = file.read_bytes()
        return found
    inst = files(installed)
    inc = files(incoming)
    if set(inst) - set(inc):
        return False
    return all(inc[rel] == data for rel, data in inst.items())

def copy_path(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        dest.symlink_to(os.readlink(src))
    elif src.is_dir():
        shutil.copytree(src, dest, symlinks=True)
    else:
        shutil.copy2(src, dest)

def remove(path):
    # is_dir() follows links. Unlink a symlink itself and leave its target.
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

def restore_symlinks(snapshot, dest):
    if snapshot.is_symlink() or not snapshot.is_dir():
        return
    for link in sorted(p for p in snapshot.rglob('*') if p.is_symlink()):
        target = dest / link.relative_to(snapshot)
        if target.exists() or target.is_symlink():
            remove(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(os.readlink(link))

def locally_edited(target, recorded, incoming=None):
    """A hand edit blocks reinstall and uninstall. A nested symlink does not.

    Reinstall may still refresh regular files that match the incoming tree.
    The link itself is preserved and is never followed.
    """
    if target.is_symlink() or not target.exists():
        return False
    if digest(target) == recorded:
        return False
    if incoming is not None and regular_files_equal(target, incoming):
        return False
    if incoming is None and target.is_dir() and any(p.is_symlink() for p in target.rglob('*')):
        return False
    return True

CLUSTER = ('centerBegin', 'center', 'centerEnd')

def find_entry(layout, widget_id):
    for section, entries in layout.items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get('id') == widget_id:
                return section, index
    return None, None

def exchange(layout, left_id, right_id):
    left = find_entry(layout, left_id)
    right = find_entry(layout, right_id)
    if left[0] is None or right[0] is None or left == right:
        return False
    # The right-hand side is evaluated first, so this is safe in one section.
    layout[left[0]][left[1]], layout[right[0]][right[1]] = layout[right[0]][right[1]], layout[left[0]][left[1]]
    return True

def cluster_ids(layout):
    found = {}
    for name in CLUSTER:
        entries = layout.get(name)
        if not isinstance(entries, list):
            found[name] = []
            continue
        found[name] = [entry.get('id') for entry in entries if isinstance(entry, dict)]
    return found

def pin_workspaces(layout):
    """Keep the workspace indicator as the only widget in the center box.

    Buttons that share that box slide it when they grow. Neighbors hang off
    the side they were already on, which is where the bar lets them grow.
    """
    section, index = find_entry(layout, 'lcars.workspaces')
    if section not in CLUSTER:
        return False
    entries = list(layout.get(section) or [])
    if section == 'center' and len(entries) == 1:
        return False
    before = entries[:index]
    widget = entries[index]
    after = entries[index + 1:]
    begin = list(layout.get('centerBegin') or [])
    center = list(layout.get('center') or [])
    end = list(layout.get('centerEnd') or [])
    if section == 'center':
        begin = begin + before
        center = [widget]
        end = after + end
    elif section == 'centerBegin':
        begin = before
        end = after + center + end
        center = [widget]
    else:
        begin = begin + center + before
        center = [widget]
        end = after
    layout['centerBegin'] = begin
    layout['center'] = center
    layout['centerEnd'] = end
    return True

def restore_cluster(layout, before_ids):
    wanted = []
    for name in CLUSTER:
        for widget_id in before_ids.get(name, []):
            wanted.append((name, widget_id))
    wanted_ids = {widget_id for _, widget_id in wanted}
    found = {}
    leftover = {name: [] for name in CLUSTER}
    for name in CLUSTER:
        for entry in list(layout.get(name) or []):
            widget_id = entry.get('id') if isinstance(entry, dict) else None
            if widget_id in wanted_ids and widget_id not in found:
                found[widget_id] = entry
            else:
                leftover[name].append(entry)
    for name in CLUSTER:
        layout[name] = [found[widget_id] for widget_id in before_ids.get(name, []) if widget_id in found]
        layout[name].extend(leftover[name])

def place_calendar_and_workspaces(bar):
    """Trade the calendar with the workspace indicator, then center the workspaces.

    A custom replacement of either widget is left where it is. The returned
    record is what uninstall reverses.
    """
    placement = {'swapped': False, 'pinned': False, 'cluster': None, 'cleared_center_anchor': False}
    layout = bar['layout']
    if find_entry(layout, 'lcars.clock')[0] is None or find_entry(layout, 'lcars.workspaces')[0] is None:
        return placement
    if not exchange(layout, 'lcars.clock', 'lcars.workspaces'):
        return placement
    placement['swapped'] = True
    placement['cluster'] = cluster_ids(layout)
    placement['pinned'] = pin_workspaces(layout)
    if bar.get('centerAnchor') in ('lcars.clock', 'omarchy.clock'):
        # The center section is the pin. A leftover clock anchor would follow
        # the calendar after it leaves the middle.
        bar.pop('centerAnchor', None)
        placement['cleared_center_anchor'] = True
    return placement

def patch_shell(original):
    d = copy.deepcopy(original)
    if d.get('version') != 1 or not isinstance(d.get('bar', {}).get('layout'), dict):
        raise RuntimeError('Unsupported shell.json format; no configuration was changed.')
    # This edition is designed for horizontal bars; do not silently move a user's bar.
    if d['bar'].get('position', 'top') not in ['top', 'bottom']:
        raise RuntimeError('LCARS requires a top or bottom bar. Move your bar first, or use --theme-only.')
    changed = {}
    for entries in d['bar']['layout'].values():
        for entry in entries:
            source = entry.get('id', '')
            if source in ['omarchy.' + name for name in SOURCES]:
                target = source.replace('omarchy.', 'lcars.', 1)
                changed[target] = copy.deepcopy(entry)
                entry['id'] = target
    anchor = d['bar'].get('centerAnchor')
    if anchor == 'omarchy.clock' and 'lcars.clock' in changed:
        d['bar']['centerAnchor'] = 'lcars.clock'
    placement = place_calendar_and_workspaces(d['bar'])
    # Stars stay in the layout and start hidden. A right-click on the bar shows them.
    left = d['bar']['layout'].setdefault('left', [])
    if not any(entry.get('id') == 'lcars.stars' for entry in left):
        left.append({'id': 'lcars.stars', 'shown': False})
    right = d['bar']['layout'].setdefault('right', [])
    right.append({'id': 'lcars.plate'})
    # Menu actions still route to the native menu; the clone only styles its bar entry.
    return d, changed, placement

def unpatch_shell(current, record):
    d = copy.deepcopy(current)
    layout = d.get('bar', {}).get('layout', {})
    placement = record.get('bar_place') or {}
    # Reverse the pin before the swap, so each entry keeps edits made after install.
    if placement.get('pinned') and placement.get('cluster'):
        restore_cluster(layout, placement['cluster'])
    if placement.get('swapped'):
        exchange(layout, 'lcars.clock', 'lcars.workspaces')
    for section, entries in layout.items():
        result = []
        for entry in entries:
            target = entry.get('id')
            if target in ['lcars.stars', 'lcars.band', 'lcars.plate']:
                continue
            if target in record['replaced']:
                entry = copy.deepcopy(entry)
                before = record['replaced'][target]
                entry['id'] = before['id']
                # Installs before the label was left alone wrote this prefix.
                if target == 'lcars.clock' and entry.get('format') == "'STARDATE' ddd HH:mm":
                    if 'format' in before:
                        entry['format'] = before['format']
                    else:
                        entry.pop('format', None)
            result.append(entry)
        layout[section] = result
    before_bar = record.get('before_shell', {}).get('bar', {})
    if placement.get('cleared_center_anchor'):
        previous = before_bar.get('centerAnchor')
        if previous:
            d['bar']['centerAnchor'] = previous
        else:
            d['bar'].pop('centerAnchor', None)
    elif d.get('bar', {}).get('centerAnchor') == 'lcars.clock':
        d['bar']['centerAnchor'] = before_bar.get('centerAnchor', '')
    before_layout = before_bar.get('layout', {})
    for name in CLUSTER:
        if name not in before_layout and not layout.get(name):
            layout.pop(name, None)
    return d

def check_hyprland():
    result = subprocess.run(['hyprctl', 'configerrors'], check=True, capture_output=True, text=True)
    if result.stdout.strip() not in ['', 'ok']:
        raise RuntimeError('Hyprland rejected the configuration: ' + result.stdout.strip())

def paths(home):
    return home / '.config/omarchy', home / '.local/state/omarchy-lcars'

def populate_stage(stage, source):
    theme_stage = stage / 'lcars'
    theme_stage.mkdir()
    for name in THEME_FILES:
        shutil.copy2(source / name, theme_stage / name)
    shutil.copytree(source / 'backgrounds', theme_stage / 'backgrounds')
    stage_palette_hooks(stage, source)
    return theme_stage

def stage_palette_hooks(stage, source):
    """Ship palette hooks. GTK4, VS Code, and Firefox ignore the plain theme palette."""
    for helper_name, wrapper_name, relative in PALETTE_HOOKS:
        helper = stage / helper_name
        shutil.copy2(source / relative, helper)
        helper.chmod(0o755)
        # Theme hooks are executed with bash, which does not honor a Python shebang.
        wrapper = stage / wrapper_name
        wrapper.write_text(
            '#!/bin/bash\n'
            f'exec python3 "$HOME/.config/omarchy/hooks/{helper_name}"\n'
        )
        wrapper.chmod(0o755)

def palette_hook_targets(config, stage):
    targets = []
    for helper_name, wrapper_name, _relative in PALETTE_HOOKS:
        targets.append((stage / helper_name, config / 'hooks' / helper_name))
        targets.append((stage / wrapper_name, config / 'hooks/theme-set.d' / wrapper_name))
    return targets

def clear_gtk4(home=None):
    script = ROOT / 'scripts/gtk4-libadwaita.py'
    if not script.is_file():
        return
    cmd = [sys.executable, str(script), '--clear']
    if home is not None:
        cmd.extend(['--home', str(home)])
    subprocess.run(cmd, check=False)

def apply_hook(home, installed_name, repo_name, extra_args=()):
    script = (home or Path.home()) / '.config/omarchy/hooks' / installed_name
    if not script.is_file():
        script = ROOT / 'scripts' / repo_name
    if not script.is_file():
        return
    cmd = [sys.executable, str(script), *extra_args]
    if home is not None:
        cmd.extend(['--home', str(home)])
    subprocess.run(cmd, check=False)

def apply_gtk4(home=None):
    apply_hook(home, GTK4_HOOK_PY, 'gtk4-libadwaita.py')

def apply_vscode(home=None):
    apply_hook(home, VSCODE_HOOK_PY, 'vscode-surfaces.py', ('--no-refresh',) if home is not None else ())

def apply_firefox(home=None):
    apply_hook(home, FIREFOX_HOOK_PY, 'firefox-chrome.py')

def clear_firefox(home=None):
    script = ROOT / 'scripts/firefox-chrome.py'
    if not script.is_file():
        return
    cmd = [sys.executable, str(script), '--clear']
    if home is not None:
        cmd.extend(['--home', str(home)])
    subprocess.run(cmd, check=False)

def apply_lcars(theme_only):
    subprocess.run(['omarchy', 'theme', 'set', 'lcars'], check=True)
    # theme-set runs the hooks; call them again so a skipped hook still paints.
    apply_gtk4()
    apply_vscode()
    apply_firefox()
    if not theme_only:
        subprocess.run(['omarchy', 'restart', 'shell'], check=True)
    subprocess.run(['hyprctl', 'reload'], check=True)
    check_hyprland()

def managed_source(target, theme_stage, source, stage):
    if target.is_symlink():
        raise RuntimeError('Refusing to replace symlink: ' + str(target))
    if target.name == 'lcars' and target.parent.name == 'themes':
        return theme_stage
    if '/plugins/' in str(target):
        plugin = source / 'plugins' / target.name
        if not plugin.exists():
            return None
        return plugin
    staged = stage / target.name
    if target.name in PALETTE_HOOK_NAMES and staged.exists():
        return staged
    raise RuntimeError('No source for managed path: ' + str(target))

def install(home, source=ROOT, theme_only=False, apply=True, omarchy_path=None, reinstall=False):
    config, state = paths(home)
    record_file = state / 'install.json'
    if record_file.exists():
        if not reinstall:
            raise RuntimeError('LCARS is already installed by this installer. Uninstall before installing another version, or reinstall with --reinstall.')
        return refresh(home, source, apply)
    if reinstall:
        raise RuntimeError('No managed LCARS installation found.')
    omarchy_path = omarchy_path or Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    if not theme_only and not (omarchy_path / 'shell/Ui/PluginBarApi.qml').exists():
        raise RuntimeError('The complete experience requires the Omarchy 4 Quickshell shell. Use --theme-only for the palette.')
    shell_file = config / 'shell.json'
    before = json.loads(shell_file.read_text()) if shell_file.exists() else None
    if not theme_only and before is None:
        raise RuntimeError('No existing shell.json. Start Omarchy once before installing widgets.')
    after, replaced, placement = (before, {}, {}) if theme_only else patch_shell(before)
    previous = home / '.local/state/omarchy/current/theme.name'
    previous_theme = previous.read_text().strip() if previous.exists() else ''
    if apply and not previous_theme:
        raise RuntimeError('Cannot determine the current theme for rollback. Start Omarchy first.')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = state / 'backups' / stamp
    stage = state / ('stage-' + stamp)
    stage.mkdir(parents=True)
    try:
        theme_stage = populate_stage(stage, source)
        targets = [(theme_stage, config / 'themes/lcars')]
        if not theme_only:
            for plugin in sorted((source / 'plugins').iterdir()):
                targets.append((plugin, config / 'plugins' / plugin.name))
        targets.extend(palette_hook_targets(config, stage))
        for _, target in targets:
            if target.is_symlink():
                raise RuntimeError('Refusing to replace symlink: ' + str(target))
            digest(target)  # Read the tree before mutation. Nested symlinks are hashed, not followed.
            if '/plugins/' in str(target) and target.exists():
                raise RuntimeError('Plugin already exists; refusing to overwrite: ' + str(target))
        if not theme_only and shell_file.is_symlink() and not Path(os.path.realpath(shell_file)).is_file():
            raise RuntimeError('Refusing to replace a symlinked shell.json.')
        backup.mkdir(parents=True)
        record = {'version': 1, 'previous_theme': previous_theme, 'before_shell': before, 'replaced': replaced, 'bar_place': placement, 'theme_only': theme_only, 'backup': str(backup), 'targets': []}
        if before is not None:
            write_json(backup / 'shell.json', before)
        try:
            for index, (src, target) in enumerate(targets):
                saved = backup / str(index)
                if target.exists():
                    copy_path(target, saved)
                entry = {'path': str(target), 'saved': str(saved) if saved.exists() else None}
                record['targets'].append(entry)
                remove(target)
                copy_path(src, target)
                entry['digest'] = digest(target)
            if not theme_only:
                write_json(shell_file, after)
            write_json(record_file, record)
            if apply:
                apply_lcars(theme_only)
        except Exception:
            for entry in reversed(record['targets']):
                target = Path(entry['path'])
                remove(target)
                if entry['saved']:
                    copy_path(Path(entry['saved']), target)
            if before is not None:
                write_json(shell_file, before)
            record_file.unlink(missing_ok=True)
            if apply and previous_theme:
                subprocess.run(['omarchy', 'theme', 'set', previous_theme], check=False)
                subprocess.run(['omarchy', 'restart', 'shell'], check=False)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return record

def refresh(home, source, apply):
    """Replace managed theme, plugin, and hook files from source, then apply LCARS.

    Shell layout and the options recorded at first install stay as they are.
    A managed file whose contents differ from the install record stops the refresh.
    """
    state = paths(home)[1]
    record_file = state / 'install.json'
    record_text = record_file.read_text()
    record = json.loads(record_text)
    if record.get('version') != 1 or not isinstance(record.get('targets'), list):
        raise RuntimeError('Unsupported LCARS install record.')
    theme_only = bool(record.get('theme_only'))
    config = paths(home)[0]
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    stage = state / ('stage-' + stamp)
    snapshot = state / ('reinstall-' + stamp)
    stage.mkdir(parents=True)
    snapshot.mkdir()
    replaced = []
    try:
        theme_stage = populate_stage(stage, source)
        checked = []
        sources = []
        existing_paths = {entry['path'] for entry in record['targets']}
        for src, target in palette_hook_targets(config, stage):
            if str(target) not in existing_paths:
                record['targets'].append({'path': str(target), 'saved': None, 'digest': None})
                existing_paths.add(str(target))
        # Plugins added after the install record was written still have to be
        # copied. A hot reload does not rebuild bar widgets already on screen.
        if not theme_only:
            for plugin in sorted((source / 'plugins').iterdir()):
                if not plugin.is_dir():
                    continue
                target = config / 'plugins' / plugin.name
                if str(target) not in existing_paths:
                    record['targets'].append({'path': str(target), 'saved': None, 'digest': None})
                    existing_paths.add(str(target))
        for entry in record['targets']:
            target = Path(entry['path'])
            if target.is_symlink():
                raise RuntimeError('Refusing to replace symlink: ' + str(target))
            if target.name in RETIRED_HOOKS:
                if locally_edited(target, entry.get('digest')):
                    raise RuntimeError('A managed file has local edits. Back up and restore it before reinstalling: ' + str(target))
                checked.append((entry, target))
                sources.append(None)
                continue
            src = managed_source(target, theme_stage, source, stage)
            if src is None:
                if target.exists():
                    raise RuntimeError('No source for managed path: ' + str(target))
                continue
            if entry.get('digest') is not None and locally_edited(target, entry.get('digest'), src):
                raise RuntimeError('A managed file has local edits. Back up and restore it before reinstalling: ' + str(target))
            checked.append((entry, target))
            sources.append(src)
        record['targets'] = [entry for entry, target in checked if target.name not in RETIRED_HOOKS]
        for index, ((entry, target), src) in enumerate(zip(checked, sources)):
            snap = snapshot / str(index)
            if target.exists():
                copy_path(target, snap)
            remove(target)
            replaced.append(index)
            if src is None:
                continue
            copy_path(src, target)
            restore_symlinks(snap, target)
            entry['digest'] = digest(target)
        write_json(record_file, record)
        if apply:
            apply_lcars(theme_only)
    except Exception:
        for index in reversed(replaced):
            target = checked[index][1]
            snap = snapshot / str(index)
            remove(target)
            if snap.exists():
                copy_path(snap, target)
        if replaced:
            record_file.write_text(record_text)
            if apply:
                subprocess.run(['omarchy', 'theme', 'set', 'lcars'], check=False)
                if not theme_only:
                    subprocess.run(['omarchy', 'restart', 'shell'], check=False)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(snapshot, ignore_errors=True)
    return record

def uninstall(home, apply=True):
    config, state = paths(home)
    record_file = state / 'install.json'
    if not record_file.exists():
        raise RuntimeError('No managed LCARS installation found.')
    record = json.loads(record_file.read_text())
    for entry in record['targets']:
        target = Path(entry['path'])
        if locally_edited(target, entry.get('digest')):
            raise RuntimeError('A managed file has local edits. Back up and restore it before uninstalling: ' + str(target))
    shell_file = config / 'shell.json'
    current = json.loads(shell_file.read_text()) if shell_file.exists() else {}
    if not record['theme_only']:
        write_json(shell_file, unpatch_shell(current, record))
    for entry in reversed(record['targets']):
        target = Path(entry['path'])
        remove(target)
        if entry['saved']:
            copy_path(Path(entry['saved']), target)
    active_file = home / '.local/state/omarchy/current/theme.name'
    active = active_file.read_text().strip() if active_file.exists() else ''
    if apply:
        if active == 'lcars' and record['previous_theme']:
            subprocess.run(['omarchy', 'theme', 'set', record['previous_theme']], check=True)
        clear_gtk4(home)
        clear_firefox(home)
        subprocess.run(['omarchy', 'restart', 'shell'], check=True)
        subprocess.run(['hyprctl', 'reload'], check=True)
        check_hyprland()
    else:
        clear_gtk4(home)
        clear_firefox(home)
    record_file.unlink()
    return record

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uninstall', action='store_true')
    p.add_argument('--reinstall', action='store_true', help='refresh managed files from this checkout and apply LCARS again')
    p.add_argument('--theme-only', action='store_true')
    p.add_argument('--no-apply', action='store_true', help='install files without reloading the live desktop')
    args = p.parse_args()
    if os.geteuid() == 0:
        p.error('Run as your desktop user, without sudo.')
    if args.reinstall and args.uninstall:
        p.error('--reinstall cannot be combined with --uninstall.')
    if args.reinstall and args.theme_only:
        p.error('--reinstall keeps the original install options. Uninstall first to change them.')
    try:
        if args.uninstall:
            record = uninstall(Path.home(), apply=not args.no_apply)
            print('LCARS uninstalled. Backup retained:', record['backup'])
        else:
            record = install(Path.home(), theme_only=args.theme_only, apply=not args.no_apply, reinstall=args.reinstall)
            if args.reinstall:
                print('LCARS reinstalled. Restart applications if they do not live-reload their theme.')
            else:
                print('LCARS installed. Backup:', record['backup'])
                print('Existing custom widgets were preserved. Restart applications if they do not live-reload their theme.')
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('LCARS:', exc, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
