import copy
import importlib.util
import json
from pathlib import Path
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
    def test_round_trip_preserves_unrelated_changes(self):
        self.install()
        d = json.loads(self.shell.read_text())
        self.assertEqual(d['bar']['layout']['center'][0]['format'], 'HH:mm')
        self.assertEqual(d['idle'], BASE['idle'])
        self.assertEqual(d['plugins'], BASE['plugins'])
        self.assertEqual(d['bar']['layout']['center'][0]['timezone'], 'Europe/Zurich')
        d['idle']['lock'] = 900
        d['bar']['layout']['right'].append({'id': 'new.widget'})
        d['bar']['layout']['center'][0]['timezone'] = 'UTC'
        m.write_json(self.shell, d)
        m.uninstall(self.home, apply=False)
        d = json.loads(self.shell.read_text())
        self.assertEqual(d['idle']['lock'], 900)
        self.assertEqual(d['bar']['layout']['right'][-1]['id'], 'new.widget')
        self.assertEqual(d['bar']['layout']['center'][0]['id'], 'omarchy.clock')
        self.assertEqual(d['bar']['layout']['center'][0]['format'], 'HH:mm')
        self.assertEqual(d['bar']['layout']['center'][0]['timezone'], 'UTC')
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
    def test_conflicting_plugin_is_not_overwritten(self):
        p = self.home/'.config/omarchy/plugins/lcars.stars/mine.qml'
        p.parent.mkdir(parents=True)
        p.write_text('personal')
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(p.read_text(), 'personal')
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_no_transparency_or_animation(self):
        self.install(animation=False, transparency=False)
        d = json.loads(self.shell.read_text())
        self.assertNotIn('lcars.stars', [x['id'] for x in d['bar']['layout']['left']])
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
