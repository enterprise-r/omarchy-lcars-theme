import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage', ROOT/'scripts/manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

BASE = {'version': 1, 'idle': {'lock': 420}, 'plugins': [{'id': 'personal.lock'}],
        'bar': {'position': 'top', 'centerAnchor': 'omarchy.clock', 'layout': {
            'left': [{'id': 'omarchy.menu'}, {'id': 'omarchy.workspaces'}, {'id': 'personal.chat'}],
            'center': [{'id': 'omarchy.clock', 'format': 'HH:mm', 'timezone': 'Europe/Zurich'}],
            'right': [{'id': 'omarchy.audio'}, {'id': 'personal.agent', 'color': 'green'}]}}}

class Installation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)/'user'
        self.shell = self.home/'.config/omarchy/shell.json'
        m.write_json(self.shell, BASE)
        self.current = self.home/'.local/state/omarchy/current/theme.name'
        self.current.parent.mkdir(parents=True)
        self.current.write_text('nord\n')
        self.platform = Path(self.tmp.name)/'platform'
        marker = self.platform/'shell/Ui/PluginBarApi.qml'
        marker.parent.mkdir(parents=True)
        marker.write_text('supported')
    def install(self, **kwargs):
        return m.install(self.home, apply=False, omarchy_path=self.platform, **kwargs)
    def source_copy(self):
        source = Path(self.tmp.name)/'src'
        (source/'scripts').mkdir(parents=True)
        for name in m.THEME_FILES:
            shutil.copy2(ROOT/name, source/name)
        shutil.copytree(ROOT/'backgrounds', source/'backgrounds')
        shutil.copytree(ROOT/'plugins', source/'plugins')
        shutil.copy2(ROOT/'scripts'/'foot-opacity.py', source/'scripts'/'foot-opacity.py')
        return source
    def test_round_trip_preserves_unrelated_changes(self):
        self.install()
        d = json.loads(self.shell.read_text())
        self.assertEqual(d['bar']['layout']['center'][0]['format'], 'HH:mm')
        ids = [x['id'] for x in d['bar']['layout']['right']]
        self.assertIn('lcars.plate', ids)
        self.assertNotIn('lcars.band', ids)
        self.assertEqual(d['idle'], BASE['idle'])
        self.assertEqual(d['plugins'], BASE['plugins'])
        self.assertEqual(d['bar']['layout']['center'][0]['timezone'], 'Europe/Zurich')
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/lcars-vscode-terminal.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/lcars-vscode-terminal.py').exists())
        foot_hook = self.home/'.config/omarchy/hooks/theme-set.d/lcars-foot-opacity.sh'
        self.assertIn('lcars-foot-opacity.py', foot_hook.read_text())
        self.assertTrue((self.home/'.config/omarchy/hooks/lcars-foot-opacity.py').is_file())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/lcars-foot-opacity.py').exists())
        d['idle']['lock'] = 900
        d['bar']['layout']['right'].append({'id': 'new.widget'})
        d['bar']['layout']['center'][0]['timezone'] = 'UTC'
        m.write_json(self.shell, d)
        m.uninstall(self.home, apply=False)
        d = json.loads(self.shell.read_text())
        self.assertEqual(d['idle']['lock'], 900)
        self.assertEqual(d['bar']['layout']['right'][-1]['id'], 'new.widget')
        self.assertNotIn('lcars.plate', [x['id'] for x in d['bar']['layout']['right']])
        self.assertEqual(d['bar']['layout']['center'][0]['id'], 'omarchy.clock')
        self.assertEqual(d['bar']['layout']['center'][0]['format'], 'HH:mm')
        self.assertEqual(d['bar']['layout']['center'][0]['timezone'], 'UTC')
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/lcars-vscode-terminal.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/lcars-foot-opacity.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/lcars-foot-opacity.py').exists())
    def test_custom_clones_are_preserved(self):
        d = copy.deepcopy(BASE)
        d['bar']['layout']['center'][0]['id'] = 'custom.clock'
        d['bar']['centerAnchor'] = 'custom.clock'
        m.write_json(self.shell, d)
        self.install()
        after = json.loads(self.shell.read_text())
        self.assertEqual(after['bar']['layout']['center'], d['bar']['layout']['center'])
        self.assertEqual(after['bar']['centerAnchor'], 'custom.clock')
    def test_existing_theme_is_restored(self):
        p = self.home/'.config/omarchy/themes/lcars/mine.txt'
        p.parent.mkdir(parents=True)
        p.write_text('personal palette')
        self.install()
        m.uninstall(self.home, apply=False)
        self.assertEqual(p.read_text(), 'personal palette')
    def test_reinstall_refuses_before_changes(self):
        self.install()
        before = self.shell.read_bytes()
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(before, self.shell.read_bytes())
    def test_reinstall_refreshes_theme_without_touching_shell(self):
        source = self.source_copy()
        personal = self.home/'.config/omarchy/themes/lcars/mine.txt'
        personal.parent.mkdir(parents=True)
        personal.write_text('personal palette')
        self.install(source=source)
        shell = json.loads(self.shell.read_text())
        shell['idle']['lock'] = 900
        m.write_json(self.shell, shell)
        yellow = 'yellow = "#abcdef"'
        colors = source/'colors.toml'
        colors.write_text(colors.read_text().replace('yellow = "#e4d58b"', yellow))
        foot = source/'foot.ini'
        foot.write_text(foot.read_text().replace('regular3=f4b965', 'regular3=abcdef'))
        record = self.install(source=source, reinstall=True)
        installed = self.home/'.config/omarchy/themes/lcars'
        self.assertIn(yellow, (installed/'colors.toml').read_text())
        self.assertIn('regular3=abcdef', (installed/'foot.ini').read_text())
        self.assertEqual(m.digest(installed), next(e['digest'] for e in record['targets'] if e['path'].endswith('/themes/lcars')))
        restored = json.loads(self.shell.read_text())
        self.assertEqual(restored['idle']['lock'], 900)
        self.assertEqual([x['id'] for x in restored['bar']['layout']['right']].count('lcars.plate'), 1)
        self.assertEqual([x['id'] for x in restored['bar']['layout']['left']].count('lcars.stars'), 1)
        m.uninstall(self.home, apply=False)
        self.assertEqual(personal.read_text(), 'personal palette')
    def test_reinstall_removes_retired_vscode_hook(self):
        source = self.source_copy()
        self.install(source=source)
        hook = self.home/'.config/omarchy/hooks/theme-set.d/lcars-vscode-terminal.sh'
        helper = self.home/'.config/omarchy/hooks/lcars-vscode-terminal.py'
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text('#!/bin/bash\nexec python3 "$HOME/.config/omarchy/hooks/lcars-vscode-terminal.py"\n')
        helper.write_text('print("old map")\n')
        record_path = self.home/'.local/state/omarchy-lcars/install.json'
        record = json.loads(record_path.read_text())
        record['targets'].extend([
            {'path': str(helper), 'saved': None, 'digest': m.digest(helper)},
            {'path': str(hook), 'saved': None, 'digest': m.digest(hook)},
        ])
        record_path.write_text(json.dumps(record))
        self.install(source=source, reinstall=True)
        self.assertFalse(hook.exists())
        self.assertFalse(helper.exists())
        saved = json.loads(record_path.read_text())
        self.assertFalse(any('lcars-vscode-terminal' in entry['path'] for entry in saved['targets']))
    def test_reinstall_keeps_opaque_install(self):
        source = self.source_copy()
        self.install(source=source, transparency=False)
        self.install(source=source, reinstall=True)
        theme = self.home/'.config/omarchy/themes/lcars'
        self.assertIn('alpha=1.0', (theme/'foot.ini').read_text())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/lcars-foot-opacity.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/lcars-foot-opacity.py').exists())
    def test_reinstall_keeps_theme_only(self):
        source = self.source_copy()
        self.install(source=source, theme_only=True)
        self.install(source=source, reinstall=True)
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
    def test_reinstall_refuses_local_edits(self):
        source = self.source_copy()
        self.install(source=source)
        colors = self.home/'.config/omarchy/themes/lcars/colors.toml'
        colors.write_text(colors.read_text()+'\n# my edit\n')
        edited = colors.read_text()
        shell = self.shell.read_bytes()
        with self.assertRaises(RuntimeError): self.install(source=source, reinstall=True)
        self.assertEqual(colors.read_text(), edited)
        self.assertEqual(self.shell.read_bytes(), shell)
    def test_reinstall_without_install_does_nothing(self):
        with self.assertRaises(RuntimeError): self.install(reinstall=True)
        self.assertFalse((self.home/'.local/state/omarchy-lcars/install.json').exists())
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_reinstall_apply_failure_restores_files(self):
        source = self.source_copy()
        self.install(source=source)
        colors = self.home/'.config/omarchy/themes/lcars/colors.toml'
        before_colors = colors.read_text()
        before_record = (self.home/'.local/state/omarchy-lcars/install.json').read_text()
        (source/'colors.toml').write_text(before_colors.replace('yellow = "#e4d58b"', 'yellow = "#abcdef"'))
        with patch.object(m.subprocess, 'run', side_effect=[subprocess.CalledProcessError(1, 'omarchy'), None, None]):
            with self.assertRaises(subprocess.CalledProcessError):
                m.install(self.home, source=source, apply=True, omarchy_path=self.platform, reinstall=True)
        self.assertEqual(colors.read_text(), before_colors)
        self.assertEqual((self.home/'.local/state/omarchy-lcars/install.json').read_text(), before_record)
        self.assertFalse(any(self.home.joinpath('.local/state/omarchy-lcars').glob('reinstall-*')))
        self.assertFalse(any(self.home.joinpath('.local/state/omarchy-lcars').glob('stage-*')))
    def test_reinstall_flag_rejects_option_changes(self):
        with patch.object(sys, 'argv', ['manage.py', '--reinstall', '--no-transparency']), patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                m.main()
    def test_conflicting_plugin_is_not_overwritten(self):
        p = self.home/'.config/omarchy/plugins/lcars.stars/mine.qml'
        p.parent.mkdir(parents=True)
        p.write_text('personal')
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(p.read_text(), 'personal')
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_no_transparency_still_ships_hidden_stars(self):
        self.install(transparency=False)
        d = json.loads(self.shell.read_text())
        self.assertIn({'id': 'lcars.stars', 'shown': False}, d['bar']['layout']['left'])
        self.assertTrue((self.home/'.config/omarchy/plugins/lcars.stars').is_dir())
        self.assertIn('lcars.plate', [x['id'] for x in d['bar']['layout']['right']])
        p = self.home/'.config/omarchy/themes/lcars'
        self.assertIn('active_opacity = 1.0', (p/'hyprland.lua').read_text())
        self.assertIn('alpha=1.0', (p/'foot.ini').read_text())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/lcars-foot-opacity.py').exists())
    def test_theme_only_does_not_change_shell(self):
        before = self.shell.read_bytes()
        self.install(theme_only=True)
        self.assertEqual(before, self.shell.read_bytes())
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
        m.uninstall(self.home, apply=False)
        self.assertEqual(before, self.shell.read_bytes())
    def test_local_edits_block_destructive_uninstall(self):
        self.install()
        p = self.home/'.config/omarchy/themes/lcars/colors.toml'
        p.write_text(p.read_text()+'\n# my edit\n')
        before = self.shell.read_bytes()
        with self.assertRaises(RuntimeError): m.uninstall(self.home, apply=False)
        self.assertEqual(before, self.shell.read_bytes())
        self.assertIn('# my edit', p.read_text())
    def test_apply_failure_rolls_back(self):
        import subprocess
        with patch.object(m.subprocess, 'run') as run:
            run.side_effect = [subprocess.CalledProcessError(1, 'omarchy'), None, None]
            with self.assertRaises(subprocess.CalledProcessError):
                m.install(self.home, apply=True, omarchy_path=self.platform)
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
        self.assertFalse((self.home/'.config/omarchy/themes/lcars').exists())
        self.assertFalse((self.home/'.local/state/omarchy-lcars/install.json').exists())
    def test_vertical_bar_rejected_without_changes(self):
        d = copy.deepcopy(BASE);d['bar']['position'] = 'left'
        m.write_json(self.shell, d)
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(json.loads(self.shell.read_text()), d)
    def test_reinstall_keeps_wallpaper_symlink(self):
        source = self.source_copy()
        self.install(source=source)
        wallpapers = Path(self.tmp.name)/'wallpapers'
        wallpapers.mkdir()
        marker = wallpapers/'keep.png'
        marker.write_bytes(b'wallpaper')
        theme = self.home/'.config/omarchy/themes/lcars'
        backgrounds = theme/'backgrounds'
        shutil.rmtree(backgrounds)
        backgrounds.symlink_to(wallpapers)
        self.install(source=source, reinstall=True)
        self.assertTrue(backgrounds.is_symlink())
        self.assertEqual(os.readlink(backgrounds), str(wallpapers))
        self.assertEqual(marker.read_bytes(), b'wallpaper')
        self.assertTrue((theme/'colors.toml').is_file())
    def test_reinstall_skips_plugins_removed_from_source(self):
        source = self.source_copy()
        self.install(source=source)
        record_path = self.home/'.local/state/omarchy-lcars/install.json'
        record = json.loads(record_path.read_text())
        ghost = self.home/'.config/omarchy/plugins/lcars.audio'
        record['targets'].append({'path': str(ghost), 'saved': None, 'digest': 'gone'})
        record_path.write_text(json.dumps(record))
        self.install(source=source, reinstall=True)
        self.assertFalse(ghost.exists())
        saved = json.loads(record_path.read_text())
        self.assertFalse(any(entry['path'].endswith('lcars.audio') for entry in saved['targets']))
    def test_install_does_not_follow_wallpaper_symlink(self):
        wallpapers = Path(self.tmp.name)/'wallpapers'
        wallpapers.mkdir()
        marker = wallpapers/'keep.png'
        marker.write_bytes(b'wallpaper')
        theme = self.home/'.config/omarchy/themes/lcars'
        theme.mkdir(parents=True)
        (theme/'backgrounds').symlink_to(wallpapers)
        (theme/'colors.toml').write_text('old\n')
        self.install()
        self.assertEqual(marker.read_bytes(), b'wallpaper')
        self.assertFalse((theme/'backgrounds').is_symlink())
        record = json.loads((self.home/'.local/state/omarchy-lcars/install.json').read_text())
        saved = Path(next(entry['saved'] for entry in record['targets'] if entry['path'].endswith('/themes/lcars')))
        self.assertTrue((saved/'backgrounds').is_symlink())
        self.assertEqual(os.readlink(saved/'backgrounds'), str(wallpapers))
        m.uninstall(self.home, apply=False)
        self.assertTrue((theme/'backgrounds').is_symlink())
        self.assertEqual(marker.read_bytes(), b'wallpaper')
    def test_symlink_target_rejected(self):
        target = Path(self.tmp.name)/'important';target.mkdir()
        p = self.home/'.config/omarchy/themes/lcars';p.parent.mkdir(parents=True)
        p.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RuntimeError): self.install()
        self.assertTrue(p.is_symlink())
    def test_symlinked_shell_json_is_written_through(self):
        versioned = Path(self.tmp.name)/'dotfiles'/'config'/'omarchy'/'shell.json'
        versioned.parent.mkdir(parents=True)
        versioned.write_bytes(self.shell.read_bytes())
        self.shell.unlink()
        self.shell.symlink_to(versioned)
        link = self.shell.readlink()
        self.install()
        self.assertEqual(self.shell.readlink(), link)
        self.assertEqual(json.loads(versioned.read_text())['bar']['layout']['center'][0]['id'], 'lcars.clock')
        self.assertFalse((versioned.parent/'shell.json.lcars-tmp').exists())
        m.uninstall(self.home, apply=False)
        self.assertEqual(self.shell.readlink(), link)
        self.assertEqual(json.loads(versioned.read_text()), BASE)

if __name__ == '__main__': unittest.main()
