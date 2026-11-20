#!/usr/bin/env python3
"""Install, reinstall, or uninstall Dark-R without replacing unrelated shell configuration.

--light installs the theme and application colors and leaves the bar alone.
The default install also replaces bar widgets.

When this repository is the theme checkout (omarchy theme install leaves it
at ~/.config/omarchy/themes/dark-r with a .git directory or gitdir file),
the installer only adds hooks and, unless --light, bar plugins. It does not
replace that directory. Update the theme with git pull. A second
omarchy theme install deletes the checkout.
"""
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
THEME = 'dark-r'
# Uninstall switches here when the theme active before install is gone.
FALLBACK_THEME = 'tokyo-night'
# Formats an older install wrote into shell.json. The Dark-R clock no longer
# reads them; uninstall still puts the previous label back on omarchy.clock.
THEME_CLOCK_FORMAT = 'yyyyMM.dd ddd HH:mm'
THEME_CLOCK_FORMATS = {"'STARDATE' ddd HH:mm", THEME_CLOCK_FORMAT}
# Used when the label from before install was itself a theme label.
STOCK_CLOCK_FORMAT = 'dddd HH:mm'
SOURCES = ['menu', 'clock', 'workspaces', 'weather', 'keyboard-layout', 'system-update', 'indicators']
# Terminal configs are not shipped: Omarchy renders them from colors.toml.
# hyprland.lua is copied only when this installer owns the theme directory.
# omarchy theme set drops every .lua file from a git checkout, so a theme
# installed with omarchy theme install takes its border colors from colors.toml.
THEME_FILES = ['colors.toml', 'shell.toml', 'hyprland.lua', 'icons.theme']
# Always shipped with the palette so GTK4/libadwaita apps can follow Dark-R.
GTK4_HOOK_PY = 'dark-r-gtk4-libadwaita.py'
GTK4_HOOK_SH = 'dark-r-gtk4.sh'
# GTK3 themes (Adwaita-dark, Omagtk) compile their colors in. Firefox and the
# GTK file chooser portal read GTK3 too.
GTK3_HOOK_PY = 'dark-r-gtk3.py'
GTK3_HOOK_SH = 'dark-r-gtk3.sh'
# Omarchy paints every VS Code surface from one background. This hook
# rewrites the generated theme with a few distinct fills.
VSCODE_HOOK_PY = 'dark-r-vscode-surfaces.py'
VSCODE_HOOK_SH = 'dark-r-vscode-surfaces.sh'
# Firefox chrome follows GTK system colors, not the libadwaita palette.
FIREFOX_HOOK_PY = 'dark-r-firefox-chrome.py'
FIREFOX_HOOK_SH = 'dark-r-firefox.sh'
# (installed helper, theme-set wrapper, path inside this repo)
PALETTE_HOOKS = (
    (GTK3_HOOK_PY, GTK3_HOOK_SH, 'scripts/gtk3.py'),
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
    temp = dest.with_name(dest.name + '.dark-r-tmp')
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
    section, index = find_entry(layout, 'dark-r.workspaces')
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
    if find_entry(layout, 'dark-r.clock')[0] is None or find_entry(layout, 'dark-r.workspaces')[0] is None:
        return placement
    if not exchange(layout, 'dark-r.clock', 'dark-r.workspaces'):
        return placement
    placement['swapped'] = True
    placement['cluster'] = cluster_ids(layout)
    placement['pinned'] = pin_workspaces(layout)
    if bar.get('centerAnchor') in ('dark-r.clock', 'omarchy.clock'):
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
        raise RuntimeError('Dark-R requires a top or bottom bar. Move your bar first, or use --light to keep the standard bar.')
    changed = {}
    for entries in d['bar']['layout'].values():
        for entry in entries:
            source = entry.get('id', '')
            if source in ['omarchy.' + name for name in SOURCES]:
                target = source.replace('omarchy.', 'dark-r.', 1)
                changed[target] = copy.deepcopy(entry)
                entry['id'] = target
    anchor = d['bar'].get('centerAnchor')
    if anchor == 'omarchy.clock' and 'dark-r.clock' in changed:
        d['bar']['centerAnchor'] = 'dark-r.clock'
    placement = place_calendar_and_workspaces(d['bar'])
    # Stars stay in the layout and start hidden. A right-click on the bar shows them.
    left = d['bar']['layout'].setdefault('left', [])
    if not any(entry.get('id') == 'dark-r.stars' for entry in left):
        left.append({'id': 'dark-r.stars', 'shown': False})
    right = d['bar']['layout'].setdefault('right', [])
    right.append({'id': 'dark-r.plate'})
    # Menu actions still route to the native menu; the clone only styles its bar entry.
    return d, changed, placement

def replaced_entry(target, record):
    """The entry a dark-r widget replaced, also for widgets added after install."""
    if target in record['replaced']:
        return record['replaced'][target]
    name = target.split('.', 1)[1] if target.startswith('dark-r.') else None
    if name not in SOURCES:
        return None
    source = 'omarchy.' + name
    layout = (record.get('before_shell') or {}).get('bar', {}).get('layout', {})
    section, index = find_entry(layout, source) if isinstance(layout, dict) else (None, None)
    return copy.deepcopy(layout[section][index]) if section is not None else {'id': source}

def stock_clock_format(omarchy_path=None):
    omarchy_path = omarchy_path or Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    try:
        stock = json.loads((omarchy_path / 'config/omarchy/shell.json').read_text())
        section, index = find_entry(stock['bar']['layout'], 'omarchy.clock')
        return stock['bar']['layout'][section][index]['format']
    except (OSError, ValueError, KeyError, TypeError):
        return STOCK_CLOCK_FORMAT

def unpatch_shell(current, record, clock_format=STOCK_CLOCK_FORMAT):
    d = copy.deepcopy(current)
    layout = d.get('bar', {}).get('layout', {})
    placement = record.get('bar_place') or {}
    # Reverse the pin before the swap, so each entry keeps edits made after install.
    # A bar already restored has no dark-r.workspaces; leave its order alone.
    if find_entry(layout, 'dark-r.workspaces')[0] is not None:
        if placement.get('pinned') and placement.get('cluster'):
            restore_cluster(layout, placement['cluster'])
        if placement.get('swapped'):
            exchange(layout, 'dark-r.clock', 'dark-r.workspaces')
    for section, entries in layout.items():
        result = []
        for entry in entries:
            target = entry.get('id')
            if target in ['dark-r.stars', 'dark-r.band', 'dark-r.plate']:
                continue
            before = replaced_entry(target, record)
            if before is not None:
                entry = copy.deepcopy(entry)
                entry['id'] = before['id']
                if entry['id'] == 'omarchy.clock' and entry.get('format') in THEME_CLOCK_FORMATS:
                    previous = before.get('format')
                    entry['format'] = previous if previous and previous not in THEME_CLOCK_FORMATS else clock_format
            result.append(entry)
        layout[section] = result
    before_bar = record.get('before_shell', {}).get('bar', {})
    if placement.get('cleared_center_anchor'):
        previous = before_bar.get('centerAnchor')
        if previous:
            d['bar']['centerAnchor'] = previous
        else:
            d['bar'].pop('centerAnchor', None)
    elif d.get('bar', {}).get('centerAnchor') == 'dark-r.clock':
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
    return home / '.config/omarchy', home / '.local/state/omarchy-dark-r'

def theme_directory(config):
    return config / 'themes' / THEME

def is_theme_checkout(path):
    """True when Omarchy cloned the theme here. Do not delete or replace it.

    A worktree stores a gitdir file at .git rather than a directory.
    A symlink is the user's own theme and is left to the existing refusal.
    """
    return path.is_dir() and not path.is_symlink() and (path / '.git').exists()

def same_path(left, right):
    return left.resolve() == right.resolve()

def require_checkout_source(source, installed):
    if same_path(source, installed):
        return
    raise RuntimeError(
        'The Dark-R theme at ' + str(installed) + ' is a git checkout. '
        'Run ./install.sh from that directory. The installer does not replace it. '
        'Update the theme with git pull. A second omarchy theme install deletes the checkout.'
    )

def without_theme_target(targets, config):
    installed = theme_directory(config)
    return [entry for entry in targets if not same_path(Path(entry['path']), installed)]

def populate_stage(stage, source):
    theme_stage = stage / THEME
    theme_stage.mkdir()
    for name in THEME_FILES:
        shutil.copy2(source / name, theme_stage / name)
    shutil.copytree(source / 'backgrounds', theme_stage / 'backgrounds')
    stage_palette_hooks(stage, source)
    return theme_stage

def stage_palette_hooks(stage, source):
    """Ship palette hooks. GTK3, GTK4, VS Code, and Firefox ignore the plain theme palette."""
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

def clear_hook(home, repo_name):
    script = ROOT / 'scripts' / repo_name
    if not script.is_file():
        return
    cmd = [sys.executable, str(script), '--clear']
    if home is not None:
        cmd.extend(['--home', str(home)])
    subprocess.run(cmd, check=False)

def clear_gtk4(home=None):
    clear_hook(home, 'gtk4-libadwaita.py')

def clear_gtk3(home=None):
    clear_hook(home, 'gtk3.py')

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
    clear_hook(home, 'firefox-chrome.py')

def apply_gtk3(home=None):
    apply_hook(home, GTK3_HOOK_PY, 'gtk3.py')

def apply_theme(theme_only):
    subprocess.run(['omarchy', 'theme', 'set', THEME], check=True)
    # theme-set runs the hooks; call them again so a skipped hook still paints.
    apply_gtk3()
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
    if target.name == THEME and target.parent.name == 'themes':
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
            raise RuntimeError('Dark-R is already installed by this installer. Uninstall before installing another version, or reinstall with --reinstall.')
        return refresh(home, source, apply)
    if reinstall:
        raise RuntimeError('No managed Dark-R installation found.')
    omarchy_path = omarchy_path or Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    if not theme_only and not (omarchy_path / 'shell/Ui/PluginBarApi.qml').exists():
        raise RuntimeError('The complete experience requires the Omarchy 4 Quickshell shell. Use --light to install the theme without bar changes.')
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
        installed = theme_directory(config)
        checkout = is_theme_checkout(installed)
        if checkout:
            require_checkout_source(source, installed)
        # The theme target is omitted for a checkout: remove() would delete
        # .git, plugins/, and scripts/ before the extensions were copied.
        targets = [] if checkout else [(theme_stage, installed)]
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
        record = {'version': 1, 'previous_theme': previous_theme, 'before_shell': before, 'replaced': replaced, 'bar_place': placement, 'theme_only': theme_only, 'theme_checkout': checkout, 'backup': str(backup), 'targets': []}
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
                apply_theme(theme_only)
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
    """Replace managed theme, plugin, and hook files from source, then apply Dark-R.

    Shell layout and the options recorded at first install stay as they are,
    including the clock format. The Dark-R clock draws its own label. A managed
    file whose contents differ from the install record stops the refresh.
    """
    state = paths(home)[1]
    record_file = state / 'install.json'
    record_text = record_file.read_text()
    record = json.loads(record_text)
    if record.get('version') != 1 or not isinstance(record.get('targets'), list):
        raise RuntimeError('Unsupported Dark-R install record.')
    theme_only = bool(record.get('theme_only'))
    config = paths(home)[0]
    installed = theme_directory(config)
    # A later omarchy theme install replaces an installer-owned copy with the
    # git checkout. Adopt that checkout instead of copying the theme again.
    if is_theme_checkout(installed):
        require_checkout_source(source, installed)
        record['theme_checkout'] = True
        record['targets'] = without_theme_target(record['targets'], config)
    elif record.get('theme_checkout'):
        record['targets'] = without_theme_target(record['targets'], config)
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
            src = managed_source(target, theme_stage, source, stage)
            if src is None:
                if target.exists():
                    raise RuntimeError('No source for managed path: ' + str(target))
                continue
            if entry.get('digest') is not None and locally_edited(target, entry.get('digest'), src):
                raise RuntimeError('A managed file has local edits. Back up and restore it before reinstalling: ' + str(target))
            checked.append((entry, target))
            sources.append(src)
        record['targets'] = [entry for entry, target in checked]
        for index, ((entry, target), src) in enumerate(zip(checked, sources)):
            snap = snapshot / str(index)
            if target.exists():
                copy_path(target, snap)
            if is_theme_checkout(target):
                raise RuntimeError('Refusing to replace the theme checkout: ' + str(target))
            remove(target)
            replaced.append(index)
            copy_path(src, target)
            restore_symlinks(snap, target)
            entry['digest'] = digest(target)
        write_json(record_file, record)
        if apply:
            apply_theme(theme_only)
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
                subprocess.run(['omarchy', 'theme', 'set', THEME], check=False)
                if not theme_only:
                    subprocess.run(['omarchy', 'restart', 'shell'], check=False)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(snapshot, ignore_errors=True)
    return record

def restore_theme(home, previous, omarchy_path=None):
    """The theme uninstall switches to: the one active before install, if it still exists."""
    omarchy_path = omarchy_path or Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    if previous and previous != THEME:
        for root in (home / '.config/omarchy/themes', omarchy_path / 'themes'):
            if (root / previous).is_dir():
                return previous
    return FALLBACK_THEME

def uninstall(home, apply=True, source=ROOT):
    config, state = paths(home)
    record_file = state / 'install.json'
    if not record_file.exists():
        raise RuntimeError('No managed Dark-R installation found.')
    record = json.loads(record_file.read_text())
    # A file that matches this checkout is the theme, including a copy that was
    # updated without a reinstall. Only a real hand edit stops uninstall.
    # A git checkout of the theme is not one of those files: uninstall removes
    # hooks and plugins and leaves the checkout for omarchy theme remove.
    installed = theme_directory(config)
    checkout = bool(record.get('theme_checkout')) or is_theme_checkout(installed)
    if is_theme_checkout(installed):
        require_checkout_source(source, installed)
    targets = without_theme_target(record['targets'], config) if checkout else record['targets']
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    stage = state / ('uninstall-check-' + stamp)
    stage.mkdir(parents=True)
    try:
        theme_stage = populate_stage(stage, source)
        for entry in targets:
            target = Path(entry['path'])
            incoming = None
            if not target.is_symlink():
                try:
                    incoming = managed_source(target, theme_stage, source, stage)
                except RuntimeError:
                    incoming = None
            if locally_edited(target, entry.get('digest'), incoming):
                raise RuntimeError('A managed file has local edits. Back up and restore it before uninstalling: ' + str(target))
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    active_file = home / '.local/state/omarchy/current/theme.name'
    active = active_file.read_text().strip() if active_file.exists() else ''
    if apply and active == THEME and not checkout:
        # Switch while the theme files still exist: a failure here leaves the
        # install whole, and the theme-set hooks clear themselves. A checkout
        # stays the active theme; only the extensions come out.
        subprocess.run(['omarchy', 'theme', 'set', restore_theme(home, record.get('previous_theme'))], check=True)
    shell_file = config / 'shell.json'
    current = json.loads(shell_file.read_text()) if shell_file.exists() else {}
    if not record['theme_only']:
        write_json(shell_file, unpatch_shell(current, record, stock_clock_format()))
    for entry in reversed(targets):
        target = Path(entry['path'])
        if is_theme_checkout(target):
            raise RuntimeError('Refusing to remove the theme checkout: ' + str(target))
        remove(target)
        if entry['saved']:
            copy_path(Path(entry['saved']), target)
    if apply:
        clear_gtk3(home)
        clear_gtk4(home)
        clear_firefox(home)
        subprocess.run(['omarchy', 'restart', 'shell'], check=True)
        subprocess.run(['hyprctl', 'reload'], check=True)
        check_hyprland()
    else:
        clear_gtk3(home)
        clear_gtk4(home)
        clear_firefox(home)
    if checkout:
        record['theme_checkout'] = True
    record_file.unlink()
    return record

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uninstall', action='store_true')
    p.add_argument('--reinstall', action='store_true', help='refresh managed files from this checkout and apply Dark-R again')
    p.add_argument('--light', action='store_true', help='install the theme and application colors; leave the standard bar unchanged')
    p.add_argument('--theme-only', action='store_true', help='same as --light')
    p.add_argument('--no-apply', action='store_true', help='install files without reloading the live desktop')
    args = p.parse_args()
    if os.geteuid() == 0:
        p.error('Run as your desktop user, without sudo.')
    light = args.light or args.theme_only
    if args.reinstall and args.uninstall:
        p.error('--reinstall cannot be combined with --uninstall.')
    if args.reinstall and light:
        p.error('--reinstall keeps the original install options. Uninstall first to change them.')
    try:
        if args.uninstall:
            record = uninstall(Path.home(), apply=not args.no_apply)
            if record.get('theme_checkout'):
                print('Dark-R extensions removed. The theme checkout was left in place. Backup retained:', record['backup'])
            else:
                print('Dark-R uninstalled. Backup retained:', record['backup'])
        else:
            record = install(Path.home(), theme_only=light, apply=not args.no_apply, reinstall=args.reinstall)
            if args.reinstall and record.get('theme_checkout'):
                print('Dark-R extensions reinstalled. The theme checkout was left in place.')
            elif args.reinstall:
                print('Dark-R reinstalled. Restart applications if they do not live-reload their theme.')
            elif record.get('theme_checkout') and light:
                print('Dark-R application colors installed. The theme checkout was left in place. Backup:', record['backup'])
            elif record.get('theme_checkout'):
                print('Dark-R bar installed. The theme checkout was left in place. Backup:', record['backup'])
                print('Existing custom widgets were preserved. Restart applications if they do not live-reload their theme.')
            elif light:
                print('Dark-R installed (light). Backup:', record['backup'])
                print('The theme and application colors are in place. The bar is unchanged.')
            else:
                print('Dark-R installed. Backup:', record['backup'])
                print('Existing custom widgets were preserved. Restart applications if they do not live-reload their theme.')
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('Dark-R:', exc, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
