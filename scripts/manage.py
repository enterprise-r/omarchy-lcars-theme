#!/usr/bin/env python3
"""Install/uninstall LCARS without replacing unrelated shell configuration."""
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
SOURCES = ['menu', 'clock', 'workspaces', 'bluetooth', 'network', 'audio', 'monitor', 'power', 'weather', 'keyboard-layout', 'system-update', 'indicators']
THEME_FILES = ['colors.toml', 'shell.toml', 'hyprland.lua', 'alacritty.toml', 'ghostty.conf', 'kitty.conf', 'foot.ini', 'icons.theme']

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
    if not path.exists():
        return None
    h = hashlib.sha256()
    files = sorted(path.rglob('*')) if path.is_dir() else [path]
    for file in files:
        if file.is_symlink():
            raise RuntimeError('Refusing symlink in managed path: ' + str(file))
        if file.is_file():
            h.update(str(file.relative_to(path) if path.is_dir() else file.name).encode())
            h.update(file.read_bytes())
    return h.hexdigest()

def copy_path(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)

def remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

def patch_shell(original, animation=True):
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
    if animation:
        d['bar']['layout'].setdefault('left', []).append({'id': 'lcars.stars'})
    right = d['bar']['layout'].setdefault('right', [])
    right.append({'id': 'lcars.plate'})
    # Menu actions still route to the native menu; the clone only styles its bar entry.
    return d, changed

def unpatch_shell(current, record):
    d = copy.deepcopy(current)
    for section, entries in d.get('bar', {}).get('layout', {}).items():
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
        d['bar']['layout'][section] = result
    if d.get('bar', {}).get('centerAnchor') == 'lcars.clock':
        d['bar']['centerAnchor'] = record['before_shell']['bar'].get('centerAnchor', '')
    return d

def check_hyprland():
    result = subprocess.run(['hyprctl', 'configerrors'], check=True, capture_output=True, text=True)
    if result.stdout.strip() not in ['', 'ok']:
        raise RuntimeError('Hyprland rejected the configuration: ' + result.stdout.strip())

def paths(home):
    return home / '.config/omarchy', home / '.local/state/omarchy-lcars'

def install(home, source=ROOT, theme_only=False, animation=True, transparency=True, apply=True, omarchy_path=None):
    config, state = paths(home)
    record_file = state / 'install.json'
    if record_file.exists():
        raise RuntimeError('LCARS is already installed by this installer. Uninstall before installing another version.')
    omarchy_path = omarchy_path or Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'))
    if not theme_only and not (omarchy_path / 'shell/Ui/PluginBarApi.qml').exists():
        raise RuntimeError('The complete experience requires the Omarchy 4 Quickshell shell. Use --theme-only for the palette.')
    shell_file = config / 'shell.json'
    before = json.loads(shell_file.read_text()) if shell_file.exists() else None
    if not theme_only and before is None:
        raise RuntimeError('No existing shell.json. Start Omarchy once before installing widgets.')
    after, replaced = (before, {}) if theme_only else patch_shell(before, animation)
    previous = home / '.local/state/omarchy/current/theme.name'
    previous_theme = previous.read_text().strip() if previous.exists() else ''
    if apply and not previous_theme:
        raise RuntimeError('Cannot determine the current theme for rollback. Start Omarchy first.')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = state / 'backups' / stamp
    stage = state / ('stage-' + stamp)
    stage.mkdir(parents=True)
    theme_stage = stage / 'lcars'
    theme_stage.mkdir()
    try:
        for name in THEME_FILES:
            shutil.copy2(source / name, theme_stage / name)
        shutil.copytree(source / 'backgrounds', theme_stage / 'backgrounds')
        if not transparency:
            p = theme_stage / 'hyprland.lua'
            p.write_text(p.read_text().replace('active_opacity = 0.97', 'active_opacity = 1.0').replace('inactive_opacity = 0.94', 'inactive_opacity = 1.0'))
            for name, old, new in [('alacritty.toml', 'opacity = 0.88', 'opacity = 1.0'), ('ghostty.conf', 'background-opacity = 0.88', 'background-opacity = 1.0'), ('kitty.conf', 'background_opacity 0.88', 'background_opacity 1.0'), ('foot.ini', 'alpha=0.88', 'alpha=1.0')]:
                p = theme_stage / name
                p.write_text(p.read_text().replace(old, new))
        targets = [(theme_stage, config / 'themes/lcars')]
        if not theme_only:
            for plugin in sorted((source / 'plugins').iterdir()):
                if plugin.name == 'lcars.stars' and not animation:
                    continue
                targets.append((plugin, config / 'plugins' / plugin.name))
        if transparency:
            helper = stage / 'lcars-foot-opacity.py'
            shutil.copy2(source / 'scripts/foot-opacity.py', helper)
            helper.chmod(0o755)
            targets.append((helper, config / 'hooks/theme-set.d/lcars-foot-opacity.py'))
        for _, target in targets:
            if target.is_symlink():
                raise RuntimeError('Refusing to replace symlink: ' + str(target))
            digest(target)  # Fail before mutation if a nested managed symlink is present.
            if '/plugins/' in str(target) and target.exists():
                raise RuntimeError('Plugin already exists; refusing to overwrite: ' + str(target))
        if not theme_only and shell_file.is_symlink() and not Path(os.path.realpath(shell_file)).is_file():
            raise RuntimeError('Refusing to replace a symlinked shell.json.')
        backup.mkdir(parents=True)
        record = {'version': 1, 'previous_theme': previous_theme, 'before_shell': before, 'replaced': replaced, 'theme_only': theme_only, 'backup': str(backup), 'targets': []}
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
                subprocess.run(['omarchy', 'theme', 'set', 'lcars'], check=True)
                if not theme_only:
                    subprocess.run(['omarchy', 'restart', 'shell'], check=True)
                subprocess.run(['hyprctl', 'reload'], check=True)
                check_hyprland()
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

def uninstall(home, apply=True):
    config, state = paths(home)
    record_file = state / 'install.json'
    if not record_file.exists():
        raise RuntimeError('No managed LCARS installation found.')
    record = json.loads(record_file.read_text())
    for entry in record['targets']:
        target = Path(entry['path'])
        if target.exists() and digest(target) != entry['digest']:
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
        subprocess.run([sys.executable, str(ROOT / 'scripts/foot-opacity.py')], check=True)
        subprocess.run(['omarchy', 'restart', 'shell'], check=True)
        subprocess.run(['hyprctl', 'reload'], check=True)
        check_hyprland()
    record_file.unlink()
    return record

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uninstall', action='store_true')
    p.add_argument('--theme-only', action='store_true')
    p.add_argument('--no-animation', action='store_true')
    p.add_argument('--no-transparency', action='store_true')
    p.add_argument('--no-apply', action='store_true', help='install files without reloading the live desktop')
    args = p.parse_args()
    if os.geteuid() == 0:
        p.error('Run as your desktop user, without sudo.')
    try:
        if args.uninstall:
            record = uninstall(Path.home(), apply=not args.no_apply)
            print('LCARS uninstalled. Backup retained:', record['backup'])
        else:
            record = install(Path.home(), theme_only=args.theme_only, animation=not args.no_animation, transparency=not args.no_transparency, apply=not args.no_apply)
            print('LCARS installed. Backup:', record['backup'])
            print('Existing custom widgets were preserved. Restart applications if they do not live-reload their theme.')
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('LCARS:', exc, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
