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
        shutil.copy2(ROOT/'scripts'/'gtk3.py', source/'scripts'/'gtk3.py')
        shutil.copy2(ROOT/'scripts'/'gtk4-libadwaita.py', source/'scripts'/'gtk4-libadwaita.py')
        shutil.copy2(ROOT/'scripts'/'vscode-surfaces.py', source/'scripts'/'vscode-surfaces.py')
        shutil.copy2(ROOT/'scripts'/'firefox-chrome.py', source/'scripts'/'firefox-chrome.py')
        return source
    def assert_gtk4_hooks(self):
        hook = self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh'
        helper = self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py'
        self.assertTrue(helper.is_file())
        self.assertIn('dark-r-gtk4-libadwaita.py', hook.read_text())
        self.assertTrue(hook.is_file())
    def assert_vscode_hooks(self):
        hook = self.home/'.config/omarchy/hooks/theme-set.d/dark-r-vscode-surfaces.sh'
        helper = self.home/'.config/omarchy/hooks/dark-r-vscode-surfaces.py'
        self.assertTrue(helper.is_file())
        self.assertIn('dark-r-vscode-surfaces.py', hook.read_text())
        self.assertTrue(hook.is_file())
    def test_gtk4_hooks_install_with_theme_only(self):
        self.install(theme_only=True)
        self.assert_gtk4_hooks()
        self.assert_vscode_hooks()
        m.uninstall(self.home, apply=False)
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-vscode-surfaces.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-vscode-surfaces.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-firefox.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-firefox-chrome.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-gtk3.py').exists())
    def test_gtk3_hook_installs(self):
        self.install(theme_only=True)
        hook = self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk3.sh'
        self.assertIn('dark-r-gtk3.py', hook.read_text())
        self.assertTrue((self.home/'.config/omarchy/hooks/dark-r-gtk3.py').is_file())
    def test_reinstall_adds_gtk4_hooks_to_old_record(self):
        source = self.source_copy()
        self.install(source=source)
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        record['targets'] = [entry for entry in record['targets'] if 'gtk4' not in entry['path']]
        for path in [
            self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py',
            self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh',
        ]:
            if path.exists():
                path.unlink()
        record_path.write_text(json.dumps(record))
        self.install(source=source, reinstall=True)
        self.assert_gtk4_hooks()
        self.assert_vscode_hooks()
        saved = json.loads(record_path.read_text())
        self.assertTrue(any(entry['path'].endswith('dark-r-gtk4-libadwaita.py') for entry in saved['targets']))
        self.assertTrue(any(entry['path'].endswith('dark-r-gtk4.sh') for entry in saved['targets']))
        self.assertTrue(any(entry['path'].endswith('dark-r-vscode-surfaces.py') for entry in saved['targets']))
        self.assertTrue(any(entry['path'].endswith('dark-r-vscode-surfaces.sh') for entry in saved['targets']))
    def test_reinstall_copies_plugins_missing_from_old_record(self):
        source = self.source_copy()
        self.install(source=source)
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        record['targets'] = [entry for entry in record['targets'] if not entry['path'].endswith('/dark-r.plate')]
        record_path.write_text(json.dumps(record))
        plate = self.home/'.config/omarchy/plugins/dark-r.plate/Plate.qml'
        plate.write_text('// stale\n')
        self.install(source=source, reinstall=True)
        self.assertIn('plateColor', plate.read_text())
        saved = json.loads(record_path.read_text())
        self.assertTrue(any(entry['path'].endswith('/dark-r.plate') for entry in saved['targets']))
    def test_gtk4_palette_generator(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('gtk4', ROOT/'scripts'/'gtk4-libadwaita.py')
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        css = g.build_css(g.load_colors(ROOT/'colors.toml'))
        # Chosen/checked is green on the showcase; amber is only hover and warn.
        self.assertIn('@define-color accent_bg_color #77af8a;', css)
        self.assertIn('@define-color accent_color #77af8a;', css)
        self.assertIn('--window-bg-color: #0c040f;', css)
        self.assertIn('--view-bg-color: #0c040f;', css)
        self.assertIn('--accent-fg-color: #0c040f;', css)
        self.assertIn('--accent-color: #77af8a;', css)
        self.assertIn('--accent-bg-color: #77af8a;', css)
        self.assertNotIn('oklab(', css)
        self.assertIn('--headerbar-bg-color: #3f2c53;', css)
        self.assertIn('--card-bg-color: #181820;', css)
        self.assertIn('--sidebar-bg-color: #181820;', css)
        self.assertIn('--popover-bg-color: #181820;', css)
        self.assertIn('--headerbar-border-color: #9385a5;', css)
        self.assertIn('--warning-bg-color: #f0a202;', css)
        self.assertIn('--success-bg-color: #77af8a;', css)
        # Selection as the showcase ::selection: --ui-border under fg-bright.
        self.assertIn('@define-color theme_selected_bg_color #3f2c53;', css)
        self.assertIn('@define-color theme_selected_fg_color #fff3e6;', css)
        self.assertIn('@define-color link_color #d2bced;', css)
        self.assertIn('@define-color borders #9385a5;', css)
        # Rules carry the roles the variables cannot.
        self.assertIn('outline-color: #fff3e6;', css)
        self.assertIn('.navigation-sidebar > row:selected', css)
        self.assertNotIn('#a5ace1', css)
        self.assertIn('@define-color insensitive_fg_color #9385a5;', css)
        # Link buttons stay links on hover; destructive stays red.
        self.assertIn(':not(.destructive-action):not(.link),', css)
        self.assertIn('button.destructive-action:hover:not(:disabled) {\n  background-color: #ffa5ad;', css)
        self.assertIn('button.suggested-action:hover:not(:disabled) {\n  background-color: #9add6d;', css)
        home = self.home
        (home/'.local/state/omarchy/current').mkdir(parents=True, exist_ok=True)
        (home/'.local/state/omarchy/current/theme.name').write_text('dark-r\n')
        theme = home/'.local/state/omarchy/current/theme'
        theme.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/'colors.toml', theme/'colors.toml')
        self.assertEqual(g.apply(home), 0)
        gtk_css = (home/'.config/gtk-4.0/gtk.css').read_text()
        self.assertIn('omarchy-dark-r.css', gtk_css)
        self.assertIn('#f0a202', (home/'.config/gtk-4.0/omarchy-dark-r.css').read_text())
        (home/'.local/state/omarchy/current/theme.name').write_text('nord\n')
        self.assertEqual(g.apply(home), 0)
        self.assertFalse((home/'.config/gtk-4.0/omarchy-dark-r.css').exists())
        self.assertFalse((home/'.config/gtk-4.0/gtk.css').exists())
        # Preserve foreign user CSS around the managed block.
        (home/'.local/state/omarchy/current/theme.name').write_text('dark-r\n')
        (home/'.config/gtk-4.0').mkdir(parents=True, exist_ok=True)
        (home/'.config/gtk-4.0/gtk.css').write_text('/* mine */\nwindow { opacity: 1; }\n')
        self.assertEqual(g.apply(home), 0)
        text = (home/'.config/gtk-4.0/gtk.css').read_text()
        self.assertIn('/* mine */', text)
        self.assertIn('BEGIN omarchy-dark-r gtk4', text)
        self.assertEqual(g.apply(home, clear=True), 0)
        self.assertEqual((home/'.config/gtk-4.0/gtk.css').read_text(), '/* mine */\nwindow { opacity: 1; }\n')
        self.assertFalse((home/'.config/gtk-4.0/omarchy-dark-r.css').exists())
    def test_vscode_surface_ramp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('vscode', ROOT/'scripts'/'vscode-surfaces.py')
        v = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v)
        colors = v.load_colors(ROOT/'colors.toml')
        workbench = v.chrome(colors)
        # Regions: code well on background, chrome on the card, header strip.
        self.assertEqual(workbench['editor.background'], '#0c040f')
        self.assertEqual(workbench['sideBar.background'], '#181820')
        self.assertEqual(workbench['activityBar.background'], '#181820')
        self.assertEqual(workbench['panel.background'], '#181820')
        self.assertEqual(workbench['titleBar.activeBackground'], '#3f2c53')
        self.assertEqual(workbench['tab.activeBackground'], workbench['editor.background'])
        self.assertNotEqual(workbench['tab.activeBackground'], workbench['tab.inactiveBackground'])
        # Separators are quiet; magenta is not a split line.
        self.assertEqual(workbench['editorGroup.border'], '#3f2c53')
        self.assertEqual(workbench['activityBar.border'], '#3f2c53')
        # Current is sage.
        self.assertEqual(workbench['tab.activeForeground'], '#77af8a')
        self.assertEqual(workbench['tab.activeBorderTop'], '#77af8a')
        self.assertEqual(workbench['activityBar.foreground'], '#77af8a')
        self.assertEqual(workbench['list.activeSelectionForeground'], '#77af8a')
        self.assertEqual(workbench['button.background'], '#77af8a')
        # Hover and keyboard rows are solid amber with dark text.
        for key in ('tab.hoverBackground', 'quickInputList.focusBackground', 'menu.selectionBackground',
                    'menubar.selectionBackground', 'editorSuggestWidget.selectedBackground',
                    'statusBarItem.hoverBackground', 'list.focusOutline'):
            self.assertEqual(workbench[key], '#f0a202', key)
        for key in ('tab.hoverForeground', 'quickInputList.focusForeground', 'menu.selectionForeground',
                    'editorSuggestWidget.selectedForeground', 'list.focusHighlightForeground',
                    'editorSuggestWidget.focusHighlightForeground'):
            self.assertEqual(workbench[key], '#0c040f', key)
        # Lists keep amber matches readable, so their fills stay quiet.
        self.assertEqual(workbench['list.highlightForeground'], '#f0a202')
        self.assertEqual(workbench['list.hoverBackground'], '#3f2c53')
        self.assertGreaterEqual(v.contrast(workbench['list.highlightForeground'], workbench['list.hoverBackground']), 4.5)
        self.assertGreaterEqual(v.contrast(workbench['list.activeSelectionForeground'], workbench['list.activeSelectionBackground']), 4.5)
        # Focus, dim, cards, links, notices.
        self.assertEqual(workbench['focusBorder'], '#fff3e6')
        for key in ('input.border', 'dropdown.border', 'checkbox.border', 'editorWidget.border',
                    'notifications.border', 'widget.border', 'descriptionForeground', 'input.placeholderForeground'):
            self.assertEqual(workbench[key], '#9385a5', key)
        self.assertEqual(workbench['textLink.foreground'], '#d2bced')
        self.assertEqual(workbench['textLink.activeForeground'], '#efe3a6')
        self.assertEqual(workbench['editorWarning.foreground'], '#f0a202')
        self.assertEqual(workbench['editorInfo.foreground'], '#a5ace1')
        self.assertEqual(workbench['editorError.foreground'], '#ec8790')
        # Editor selection is the opaque --ui-border fill, as the showcase ::selection.
        self.assertEqual(workbench['editor.selectionBackground'], '#3f2c53')
        self.assertGreaterEqual(v.contrast(workbench['editor.selectionBackground'], workbench['editor.background']), 1.5)
        self.assertGreaterEqual(v.contrast('#e0e6e2', workbench['editor.selectionBackground']), 7)
        # No translucent washes for UI hover or selection.
        for key in ('tab.hoverBackground', 'toolbar.hoverBackground', 'list.hoverBackground',
                    'editor.selectionBackground', 'terminal.selectionBackground',
                    'menubar.selectionBackground', 'activityBar.activeBackground', 'list.focusOutline'):
            self.assertEqual(len(workbench[key]), 7, key)
        home = self.home
        state = home/'.local/state/omarchy/current'
        state.mkdir(parents=True, exist_ok=True)
        (state/'theme.name').write_text('dark-r\n')
        theme = state/'theme'
        theme.mkdir()
        shutil.copy2(ROOT/'colors.toml', theme/'colors.toml')
        (theme/'vscode-theme.json').write_text(json.dumps({
            'name': 'Omarchy',
            'colors': {
                'editor.background': '#0c040f',
                'sideBar.background': '#0c040f',
                'activityBar.background': '#0c040f',
                'panel.background': '#0c040f',
                'tab.activeBackground': '#0c040f',
                'tab.inactiveBackground': '#0c040f',
            },
            'tokenColors': [{'name': 'Comment'}],
        }))
        self.assertEqual(v.apply(home, refresh=False), 0)
        patched = json.loads((theme/'vscode-theme.json').read_text())
        self.assertEqual(patched['tokenColors'], [{'name': 'Comment'}])
        self.assertEqual(patched['colors']['editor.background'], '#0c040f')
        self.assertEqual(patched['colors']['sideBar.background'], workbench['sideBar.background'])
        self.assertEqual(patched['colors']['activityBar.background'], workbench['activityBar.background'])
        self.assertEqual(patched['colors']['panel.background'], workbench['panel.background'])
        self.assertEqual(patched['colors']['tab.inactiveBackground'], workbench['tab.inactiveBackground'])
        self.assertEqual(patched['colors']['titleBar.activeBackground'], '#3f2c53')
        self.assertEqual(v.apply(home, refresh=False), 0)
        (state/'theme.name').write_text('nord\n')
        (theme/'vscode-theme.json').write_text(json.dumps({'colors': {'editor.background': '#111111'}}))
        self.assertEqual(v.apply(home, refresh=False), 0)
        self.assertEqual(json.loads((theme/'vscode-theme.json').read_text())['colors']['editor.background'], '#111111')
    def test_firefox_palette(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('firefox', ROOT/'scripts'/'firefox-chrome.py')
        f = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(f)
        css = f.build_chrome(f.load_colors(ROOT/'colors.toml'))
        self.assertIn('--toolbar-background-color: #3f2c53 !important;', css)
        self.assertIn('--color-accent-primary: #77af8a !important;', css)
        self.assertIn('--link-color: #d2bced !important;', css)
        self.assertIn('--focus-outline-color: #fff3e6 !important;', css)
        self.assertIn('--urlbarview-background-color-selected: #f0a202 !important;', css)
        self.assertIn('--urlbarview-text-color-selected: #0c040f !important;', css)
        # Selected tab is sage; destructive stays red, brighter on hover.
        self.assertIn('--tab-border-color-selected: #77af8a !important;', css)
        self.assertIn('--tab-border-color-selected-leading: #77af8a !important;', css)
        self.assertIn('--tab-border-color-selected-trailing: #77af8a !important;', css)
        self.assertIn('--button-background-color-destructive: #ec8790 !important;', css)
        self.assertIn('--button-background-color-destructive-hover: #ffa5ad !important;', css)
        self.assertIn('--panel-background-color: #181820 !important;', css)
        self.assertNotIn('.tab-background', css)
        home = self.home
        state = home/'.local/state/omarchy/current'
        state.mkdir(parents=True, exist_ok=True)
        (state/'theme.name').write_text('dark-r\n')
        theme = state/'theme'
        theme.mkdir()
        shutil.copy2(ROOT/'colors.toml', theme/'colors.toml')
        profile = home/'.config/mozilla/firefox/abc.default-release'
        profile.mkdir(parents=True)
        webapp = home/'.config/mozilla/firefox/web.WebApps'
        webapp.mkdir()
        (home/'.config/mozilla/firefox/profiles.ini').write_text(
            '[Profile0]\nName=default-release\nIsRelative=1\nPath=abc.default-release\n'
            '\n[Profile1]\nName=WebApps\nIsRelative=1\nPath=web.WebApps\n'
        )
        (profile/'chrome').mkdir()
        (profile/'chrome/userChrome.css').write_text('/* mine */\n#urlbar { opacity: 1; }\n')
        (profile/'user.js').write_text('user_pref("browser.startup.page", 1);\n')
        self.assertEqual(f.apply(home), 0)
        chrome = (profile/'chrome/userChrome.css').read_text()
        self.assertIn('/* mine */', chrome)
        self.assertIn('omarchy-dark-r.css', chrome)
        sheet = (profile/'chrome/omarchy-dark-r.css').read_text()
        self.assertIn('#f0a202', sheet)
        self.assertIn('#3f2c53', sheet)
        self.assertIn('#77af8a', sheet)
        self.assertFalse((webapp/'chrome/omarchy-dark-r.css').exists())
        prefs = (profile/'user.js').read_text()
        self.assertIn('toolkit.legacyUserProfileCustomizations.stylesheets', prefs)
        self.assertIn('browser.startup.page', prefs)
        (state/'theme.name').write_text('nord\n')
        self.assertEqual(f.apply(home), 0)
        self.assertFalse((profile/'chrome/omarchy-dark-r.css').exists())
        self.assertEqual((profile/'chrome/userChrome.css').read_text(), '/* mine */\n#urlbar { opacity: 1; }\n')
        self.assertEqual((profile/'user.js').read_text(), 'user_pref("browser.startup.page", 1);\n')
    def test_round_trip_preserves_unrelated_changes(self):
        self.install()
        self.assert_gtk4_hooks()
        d = json.loads(self.shell.read_text())
        # keep the rest of the original test body by re-reading below marker if needed
        clock = next(x for x in d['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
        self.assertEqual(clock['format'], 'HH:mm')
        ids = [x['id'] for x in d['bar']['layout']['right']]
        self.assertIn('dark-r.plate', ids)
        self.assertNotIn('dark-r.band', ids)
        self.assertEqual(d['idle'], BASE['idle'])
        self.assertEqual(d['plugins'], BASE['plugins'])
        self.assertEqual(clock['timezone'], 'Europe/Zurich')
        self.assertEqual(d['bar']['layout']['center'][0]['id'], 'dark-r.workspaces')
        self.assertNotIn('centerAnchor', d['bar'])
        self.assert_vscode_hooks()
        theme = self.home/'.config/omarchy/themes/dark-r'
        for name in ('alacritty.toml', 'kitty.conf', 'ghostty.conf', 'foot.ini'):
            self.assertFalse((theme/name).exists())  # Omarchy renders these from colors.toml.
        d['idle']['lock'] = 900
        d['bar']['layout']['right'].append({'id': 'new.widget'})
        clock['timezone'] = 'UTC'
        m.write_json(self.shell, d)
        m.uninstall(self.home, apply=False)
        d = json.loads(self.shell.read_text())
        self.assertEqual(d['idle']['lock'], 900)
        self.assertEqual(d['bar']['layout']['right'][-1]['id'], 'new.widget')
        self.assertNotIn('dark-r.plate', [x['id'] for x in d['bar']['layout']['right']])
        self.assertEqual(d['bar']['layout']['center'][0]['id'], 'omarchy.clock')
        self.assertEqual(d['bar']['layout']['center'][0]['format'], 'HH:mm')
        self.assertEqual(d['bar']['layout']['center'][0]['timezone'], 'UTC')
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-gtk4.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-gtk4-libadwaita.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-vscode-surfaces.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-vscode-surfaces.py').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/theme-set.d/dark-r-firefox.sh').exists())
        self.assertFalse((self.home/'.config/omarchy/hooks/dark-r-firefox-chrome.py').exists())
    def test_center_group_stays_beside_the_workspaces(self):
        d = copy.deepcopy(BASE)
        d['bar']['layout']['centerBegin'] = [{'id': 'personal.before'}]
        d['bar']['layout']['center'] = [
            {'id': 'omarchy.indicators'},
            {'id': 'omarchy.clock', 'format': 'HH:mm', 'timezone': 'Europe/Zurich'},
            {'id': 'omarchy.elsewhen'},
        ]
        d['bar']['layout']['centerEnd'] = [{'id': 'personal.after'}]
        m.write_json(self.shell, d)
        self.install()
        laid = json.loads(self.shell.read_text())['bar']['layout']
        self.assertEqual([x['id'] for x in laid['centerBegin']], ['personal.before', 'dark-r.indicators'])
        self.assertEqual([x['id'] for x in laid['center']], ['dark-r.workspaces'])
        self.assertEqual([x['id'] for x in laid['centerEnd']], ['omarchy.elsewhen', 'personal.after'])
        self.assertEqual(laid['left'][1]['id'], 'dark-r.clock')
        self.assertEqual(laid['left'][1]['format'], 'HH:mm')
        current = json.loads(self.shell.read_text())
        current['bar']['layout']['centerEnd'].append({'id': 'new.widget'})
        m.write_json(self.shell, current)
        m.uninstall(self.home, apply=False)
        restored = json.loads(self.shell.read_text())
        layout = restored['bar']['layout']
        self.assertEqual([x['id'] for x in layout['center']], ['omarchy.indicators', 'omarchy.clock', 'omarchy.elsewhen'])
        self.assertEqual(layout['center'][1]['timezone'], 'Europe/Zurich')
        self.assertEqual([x['id'] for x in layout['left']], ['omarchy.menu', 'omarchy.workspaces', 'personal.chat'])
        self.assertEqual(layout['centerEnd'][-1]['id'], 'new.widget')
        self.assertEqual([x['id'] for x in layout['centerBegin']], ['personal.before'])
        self.assertEqual(restored['bar']['centerAnchor'], 'omarchy.clock')
    def test_uninstall_reverts_widgets_missing_from_record(self):
        # A widget renamed on the bar but absent from the record still goes back.
        d = copy.deepcopy(BASE)
        d['bar']['layout']['center'].insert(0, {'id': 'omarchy.indicators', 'size': 2})
        m.write_json(self.shell, d)
        self.install()
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        del record['replaced']['dark-r.indicators']
        record_path.write_text(json.dumps(record))
        m.uninstall(self.home, apply=False)
        layout = json.loads(self.shell.read_text())['bar']['layout']
        self.assertEqual(layout['center'][0], {'id': 'omarchy.indicators', 'size': 2})
        self.assertFalse(any(x['id'].startswith('dark-r.') for entries in layout.values() for x in entries))
    def test_uninstall_twice_keeps_the_restored_bar(self):
        d = copy.deepcopy(BASE)
        d['bar']['layout']['center'] = [
            {'id': 'omarchy.indicators'},
            {'id': 'omarchy.clock', 'format': 'HH:mm'},
            {'id': 'omarchy.elsewhen'},
            {'id': 'personal.music'},
        ]
        m.write_json(self.shell, d)
        self.install()
        record = json.loads((self.home/'.local/state/omarchy-dark-r/install.json').read_text())
        once = m.unpatch_shell(json.loads(self.shell.read_text()), record)
        self.assertEqual([x['id'] for x in once['bar']['layout']['center']],
                         ['omarchy.indicators', 'omarchy.clock', 'omarchy.elsewhen', 'personal.music'])
        self.assertEqual(m.unpatch_shell(once, record), once)
    def test_uninstall_switches_theme_before_removing_it(self):
        self.current.write_text('dark-r\n')  # an unmanaged copy was active at install
        self.install()
        record = json.loads((self.home/'.local/state/omarchy-dark-r/install.json').read_text())
        self.assertEqual(record['previous_theme'], 'dark-r')
        theme_dir = self.home/'.config/omarchy/themes/dark-r'
        seen = []
        def run(cmd, *args, **kwargs):
            if cmd[:3] == ['omarchy', 'theme', 'set']:
                seen.append((cmd[3], theme_dir.exists()))
            return subprocess.CompletedProcess(cmd, 0, '', '')
        with patch.object(m.subprocess, 'run', side_effect=run), patch.object(m, 'check_hyprland'):
            m.uninstall(self.home)
        self.assertEqual(seen, [(m.FALLBACK_THEME, True)])
        self.assertFalse(theme_dir.exists())
    def test_failed_theme_switch_leaves_install_whole(self):
        self.current.write_text('dark-r\n')
        self.install()
        def run(cmd, *args, **kwargs):
            if cmd[:3] == ['omarchy', 'theme', 'set']:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0, '', '')
        before = self.shell.read_text()
        with patch.object(m.subprocess, 'run', side_effect=run), patch.object(m, 'check_hyprland'):
            with self.assertRaises(subprocess.CalledProcessError):
                m.uninstall(self.home)
        self.assertTrue((self.home/'.config/omarchy/themes/dark-r').is_dir())
        self.assertTrue((self.home/'.config/omarchy/plugins/dark-r.clock').is_dir())
        self.assertEqual(self.shell.read_text(), before)
        self.assertTrue((self.home/'.local/state/omarchy-dark-r/install.json').exists())
    def test_restore_theme_prefers_an_existing_previous_theme(self):
        platform = Path(self.tmp.name)/'platform'
        (platform/'themes/nord').mkdir(parents=True)
        self.assertEqual(m.restore_theme(self.home, 'nord', platform), 'nord')
        self.assertEqual(m.restore_theme(self.home, 'gone', platform), m.FALLBACK_THEME)
        self.assertEqual(m.restore_theme(self.home, 'dark-r', platform), m.FALLBACK_THEME)
        self.assertEqual(m.restore_theme(self.home, '', platform), m.FALLBACK_THEME)
    def test_uninstall_resets_theme_clock_formats(self):
        for before, expected in (('HH:mm', 'HH:mm'), ('yyyyMM.dd ddd HH:mm', 'dddd HH:mm')):
            with self.subTest(before=before):
                self.setUp()
                d = copy.deepcopy(BASE)
                d['bar']['layout']['center'][0]['format'] = before
                m.write_json(self.shell, d)
                self.install()
                current = json.loads(self.shell.read_text())
                clock = next(x for x in current['bar']['layout']['left'] if x['id'] == 'dark-r.clock')
                clock['format'] = 'yyyyMM.dd ddd HH:mm'
                m.write_json(self.shell, current)
                with patch.dict(os.environ, {'OMARCHY_PATH': str(self.platform)}):
                    m.uninstall(self.home, apply=False)
                clock = json.loads(self.shell.read_text())['bar']['layout']['center'][0]
                self.assertEqual((clock['id'], clock['format']), ('omarchy.clock', expected))
                self.tearDown()
    def test_stock_clock_format_comes_from_omarchy(self):
        stock = self.platform/'config/omarchy/shell.json'
        stock.parent.mkdir(parents=True)
        stock.write_text(json.dumps({'bar': {'layout': {'center': [{'id': 'omarchy.clock', 'format': 'ddd HH:mm'}]}}}))
        self.assertEqual(m.stock_clock_format(self.platform), 'ddd HH:mm')
        stock.unlink()
        self.assertEqual(m.stock_clock_format(self.platform), m.STOCK_CLOCK_FORMAT)
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
        p = self.home/'.config/omarchy/themes/dark-r/mine.txt'
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
        personal = self.home/'.config/omarchy/themes/dark-r/mine.txt'
        personal.parent.mkdir(parents=True)
        personal.write_text('personal palette')
        self.install(source=source)
        shell = json.loads(self.shell.read_text())
        shell['idle']['lock'] = 900
        m.write_json(self.shell, shell)
        yellow = 'yellow = "#abcdef"'
        colors = source/'colors.toml'
        colors.write_text(colors.read_text().replace('yellow = "#e4d58b"', yellow))
        record = self.install(source=source, reinstall=True)
        installed = self.home/'.config/omarchy/themes/dark-r'
        self.assertIn(yellow, (installed/'colors.toml').read_text())
        self.assertEqual(m.digest(installed), next(e['digest'] for e in record['targets'] if e['path'].endswith('/themes/dark-r')))
        restored = json.loads(self.shell.read_text())
        self.assertEqual(restored['idle']['lock'], 900)
        self.assertEqual([x['id'] for x in restored['bar']['layout']['right']].count('dark-r.plate'), 1)
        self.assertEqual([x['id'] for x in restored['bar']['layout']['left']].count('dark-r.stars'), 1)
        m.uninstall(self.home, apply=False)
        self.assertEqual(personal.read_text(), 'personal palette')
    def test_reinstall_drops_old_terminal_configs(self):
        source = self.source_copy()
        self.install(source=source)
        theme = self.home/'.config/omarchy/themes/dark-r'
        (theme/'foot.ini').write_text('[colors-dark]\nalpha=0.85\n')
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        next(e for e in record['targets'] if e['path'].endswith('/themes/dark-r'))['digest'] = m.digest(theme)
        record_path.write_text(json.dumps(record))
        self.install(source=source, reinstall=True)
        self.assertFalse((theme/'foot.ini').exists())
    def test_reinstall_keeps_theme_only(self):
        source = self.source_copy()
        self.install(source=source, theme_only=True)
        self.install(source=source, reinstall=True)
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
    def test_reinstall_refuses_local_edits(self):
        source = self.source_copy()
        self.install(source=source)
        colors = self.home/'.config/omarchy/themes/dark-r/colors.toml'
        colors.write_text(colors.read_text()+'\n# my edit\n')
        edited = colors.read_text()
        shell = self.shell.read_bytes()
        with self.assertRaises(RuntimeError): self.install(source=source, reinstall=True)
        self.assertEqual(colors.read_text(), edited)
        self.assertEqual(self.shell.read_bytes(), shell)
    def test_reinstall_without_install_does_nothing(self):
        with self.assertRaises(RuntimeError): self.install(reinstall=True)
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/install.json').exists())
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_reinstall_apply_failure_restores_files(self):
        source = self.source_copy()
        self.install(source=source)
        colors = self.home/'.config/omarchy/themes/dark-r/colors.toml'
        before_colors = colors.read_text()
        before_record = (self.home/'.local/state/omarchy-dark-r/install.json').read_text()
        (source/'colors.toml').write_text(before_colors.replace('yellow = "#e4d58b"', 'yellow = "#abcdef"'))
        with patch.object(m.subprocess, 'run', side_effect=[subprocess.CalledProcessError(1, 'omarchy'), None, None]):
            with self.assertRaises(subprocess.CalledProcessError):
                m.install(self.home, source=source, apply=True, omarchy_path=self.platform, reinstall=True)
        self.assertEqual(colors.read_text(), before_colors)
        self.assertEqual((self.home/'.local/state/omarchy-dark-r/install.json').read_text(), before_record)
        self.assertFalse(any(self.home.joinpath('.local/state/omarchy-dark-r').glob('reinstall-*')))
        self.assertFalse(any(self.home.joinpath('.local/state/omarchy-dark-r').glob('stage-*')))
    def test_reinstall_flag_rejects_option_changes(self):
        with patch.object(sys, 'argv', ['manage.py', '--reinstall', '--theme-only']), patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit):
                m.main()
    def test_conflicting_plugin_is_not_overwritten(self):
        p = self.home/'.config/omarchy/plugins/dark-r.stars/mine.qml'
        p.parent.mkdir(parents=True)
        p.write_text('personal')
        with self.assertRaises(RuntimeError): self.install()
        self.assertEqual(p.read_text(), 'personal')
        self.assertEqual(json.loads(self.shell.read_text()), BASE)
    def test_install_ships_hidden_stars(self):
        self.install()
        d = json.loads(self.shell.read_text())
        self.assertIn({'id': 'dark-r.stars', 'shown': False}, d['bar']['layout']['left'])
        self.assertTrue((self.home/'.config/omarchy/plugins/dark-r.stars').is_dir())
        self.assertIn('dark-r.plate', [x['id'] for x in d['bar']['layout']['right']])
        # Opacity belongs to Omarchy's Glassy toggle, not the theme.
        self.assertNotIn('_opacity', (self.home/'.config/omarchy/themes/dark-r/hyprland.lua').read_text())
    def test_theme_only_does_not_change_shell(self):
        before = self.shell.read_bytes()
        self.install(theme_only=True)
        self.assertEqual(before, self.shell.read_bytes())
        self.assertFalse((self.home/'.config/omarchy/plugins').exists())
        m.uninstall(self.home, apply=False)
        self.assertEqual(before, self.shell.read_bytes())
    def test_local_edits_block_destructive_uninstall(self):
        self.install()
        p = self.home/'.config/omarchy/themes/dark-r/colors.toml'
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
        self.assertFalse((self.home/'.config/omarchy/themes/dark-r').exists())
        self.assertFalse((self.home/'.local/state/omarchy-dark-r/install.json').exists())
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
        theme = self.home/'.config/omarchy/themes/dark-r'
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
        record_path = self.home/'.local/state/omarchy-dark-r/install.json'
        record = json.loads(record_path.read_text())
        ghost = self.home/'.config/omarchy/plugins/dark-r.audio'
        record['targets'].append({'path': str(ghost), 'saved': None, 'digest': 'gone'})
        record_path.write_text(json.dumps(record))
        self.install(source=source, reinstall=True)
        self.assertFalse(ghost.exists())
        saved = json.loads(record_path.read_text())
        self.assertFalse(any(entry['path'].endswith('dark-r.audio') for entry in saved['targets']))
    def test_install_does_not_follow_wallpaper_symlink(self):
        wallpapers = Path(self.tmp.name)/'wallpapers'
        wallpapers.mkdir()
        marker = wallpapers/'keep.png'
        marker.write_bytes(b'wallpaper')
        theme = self.home/'.config/omarchy/themes/dark-r'
        theme.mkdir(parents=True)
        (theme/'backgrounds').symlink_to(wallpapers)
        (theme/'colors.toml').write_text('old\n')
        self.install()
        self.assertEqual(marker.read_bytes(), b'wallpaper')
        self.assertFalse((theme/'backgrounds').is_symlink())
        record = json.loads((self.home/'.local/state/omarchy-dark-r/install.json').read_text())
        saved = Path(next(entry['saved'] for entry in record['targets'] if entry['path'].endswith('/themes/dark-r')))
        self.assertTrue((saved/'backgrounds').is_symlink())
        self.assertEqual(os.readlink(saved/'backgrounds'), str(wallpapers))
        m.uninstall(self.home, apply=False)
        self.assertTrue((theme/'backgrounds').is_symlink())
        self.assertEqual(marker.read_bytes(), b'wallpaper')
    def test_symlink_target_rejected(self):
        target = Path(self.tmp.name)/'important';target.mkdir()
        p = self.home/'.config/omarchy/themes/dark-r';p.parent.mkdir(parents=True)
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
        self.assertEqual(json.loads(versioned.read_text())['bar']['layout']['center'][0]['id'], 'dark-r.workspaces')
        self.assertEqual(json.loads(versioned.read_text())['bar']['layout']['left'][1]['id'], 'dark-r.clock')
        self.assertFalse((versioned.parent/'shell.json.dark-r-tmp').exists())
        m.uninstall(self.home, apply=False)
        self.assertEqual(self.shell.readlink(), link)
        self.assertEqual(json.loads(versioned.read_text()), BASE)

def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class PaletteHooks(unittest.TestCase):
    """GTK3, GTK4 and Firefox paint the same Dark-R roles."""
    def setUp(self):
        self.gtk3 = load_script('gtk3')
        self.gtk = load_script('gtk4-libadwaita')
        self.firefox = load_script('firefox-chrome')
        self.colors = self.gtk.load_colors(ROOT/'colors.toml')
    def roles_block(self, name):
        text = (ROOT/'scripts'/f'{name}.py').read_text()
        return text[text.index('# ROLES-BEGIN'):text.index('# ROLES-END')]
    def test_role_code_is_identical(self):
        self.assertEqual(self.roles_block('gtk4-libadwaita'), self.roles_block('firefox-chrome'))
        self.assertEqual(self.roles_block('gtk4-libadwaita'), self.roles_block('gtk3'))
        self.assertEqual(self.roles_block('gtk4-libadwaita'), self.roles_block('vscode-surfaces'))
    def outputs(self):
        vscode = load_script('vscode-surfaces')
        return {
            'gtk3': self.gtk3.build_css(self.colors),
            'gimp': self.gtk3.build_gimp_css(self.colors),
            'gtk4': self.gtk.build_css(self.colors),
            'firefox chrome': self.firefox.build_chrome(self.colors),
            'firefox content': self.firefox.build_content(self.colors),
            'vscode': json.dumps(vscode.chrome(vscode.load_colors(ROOT/'colors.toml'))),
        }
    def test_hooks_use_palette_colors_only(self):
        import re, tomllib
        palette = {v.lower() for v in tomllib.loads((ROOT/'colors.toml').read_text()).values()
                   if isinstance(v, str) and v.startswith('#')}
        for name, text in self.outputs().items():
            # A two-digit alpha suffix on a palette color is still the palette.
            for color in re.findall(r'#[0-9a-fA-F]{6}(?![0-9a-fA-F]{1}\b)', text):
                self.assertIn(color.lower(), palette, name)
            self.assertNotRegex(text, r'\b(alpha|rgba?|mix|shade|oklab)\(', name)
    def test_css_hooks_set_colors_not_shapes(self):
        import re
        for name in ('gtk3', 'gimp', 'gtk4', 'firefox chrome', 'firefox content'):
            text = self.outputs()[name]
            self.assertNotRegex(text, r'\b(border-width|border-style|border-radius|padding|margin|min-width|min-height|font|text-shadow|-gtk-icon-shadow)\s*:', name)
            self.assertNotRegex(text, r'\bbackground\s*:', name)
            # Box shadows only where Adwaita draws a line with one.
            for shadow in re.findall(r'box-shadow:\s*([^;]*);', text):
                self.assertRegex(shadow, r'^inset (0 0 0 1px|0 -?4px|-?4px 0) #', name)
    def test_gtk3_keeps_adwaita_shapes(self):
        css = self.gtk3.build_css(self.colors)
        r = self.gtk.roles(self.colors)
        self.assertIn(f'notebook > header.top > tabs > tab:checked {{ box-shadow: inset 0 -4px {r["primary"]}; }}', css)
        self.assertIn(f'infobar.error > revealer > box {{ border-bottom-color: {r["error"]}; }}', css)
        self.assertIn(':not(:link):not(:visited),', css)
        self.assertIn(f'button.destructive-action:hover:not(:disabled) {{\n  background-color: {r["error_hover"]};', css)
        self.assertNotIn('button:active', css)
    def test_header_and_menus_match(self):
        gtk = self.gtk.build_css(self.colors)
        firefox = self.firefox.build_chrome(self.colors)
        r = self.gtk.roles(self.colors)
        self.assertIn(f'--headerbar-bg-color: {r["bar"]};', gtk)
        self.assertIn(f'--toolbar-background-color: {r["bar"]} !important;', firefox)
        self.assertIn(f'--popover-bg-color: {r["card"]};', gtk)
        self.assertIn(f'--panel-background-color: {r["card"]} !important;', firefox)
        self.assertIn(f'--accent-bg-color: {r["primary"]};', gtk)
        self.assertIn(f'--color-accent-primary: {r["primary"]} !important;', firefox)
    def test_roles_follow_showcase(self):
        r = self.gtk.roles(self.colors)
        self.assertEqual(r['bar'], '#3f2c53')
        # Cyan is the space in view: active window, focused field.
        self.assertEqual(r['active'], '#96c5cf')
        self.assertEqual(r['hover'], '#f0a202')
        self.assertEqual(r['primary'], '#77af8a')
        self.assertEqual(r['focus'], '#fff3e6')
        self.assertEqual(r['warn'], '#f0a202')
        self.assertEqual(r['link'], '#d2bced')
    def test_active_and_menu_roles(self):
        import tomllib
        shell = tomllib.loads((ROOT/'shell.toml').read_text())
        colors = tomllib.loads((ROOT/'colors.toml').read_text())
        self.assertEqual(colors['hyprland_active_border'], colors['cyan'])
        self.assertIn('rgba(96c5cfff)', (ROOT/'hyprland.lua').read_text())
        self.assertEqual(shell['lock']['border-active'], colors['cyan'])
        # The Omarchy menu highlight is sage; the launcher keeps amber.
        self.assertEqual(shell['menu']['selected-background'], colors['green'])
        self.assertEqual(shell['launcher']['selected-background'], colors['accent'])
        workspaces = (ROOT/'plugins/dark-r.workspaces/Workspaces.qml').read_text()
        self.assertIn('segment.focused ? "#96c5cf" : (segment.occupied ? "#77af8a"', workspaces)
        self.assertEqual(shell['notifications']['border'], colors['accent'])
    def test_text_on_fills_reads(self):
        r = self.gtk.roles(self.colors)
        for fill in ('primary', 'hover', 'error', 'warn', 'ok'):
            text = self.gtk.on_color(r[fill], r['bg'], r['fg'])
            self.assertGreaterEqual(self.gtk.contrast(r[fill], text), 4.5, fill)
    def test_no_translucent_washes(self):
        # Translucent amber over the dark surfaces reads as brown.
        for css in (self.gtk3.build_css(self.colors), self.gtk.build_css(self.colors), self.firefox.build_chrome(self.colors),
                    self.firefox.build_content(self.colors)):
            self.assertNotIn('color-mix', css)
    def test_firefox_button_text_stays_light(self):
        # --button-text-color is also panel menu text.
        self.assertNotIn('--button-text-color:', self.firefox.build_chrome(self.colors))
    def test_gtk4_window_controls_hover_round(self):
        css = self.gtk.build_css(self.colors)
        button = css.index('windowcontrols > button:hover:not(')
        self.assertGreater(button, css.index('/* Hover: solid amber'))
        self.assertIn('background-color: transparent;', css[button:button + 200])
        image = css.index('windowcontrols > button:hover > image {')
        self.assertIn('#f0a202', css[image:image + 120])
    def test_hover_is_solid_amber_with_dark_text(self):
        gtk = self.gtk.build_css(self.colors)
        chrome = self.firefox.build_chrome(self.colors)
        self.assertIn('--toolbarbutton-background-color-hover: #f0a202 !important;', chrome)
        self.assertIn('--button-text-color-hover: #0c040f !important;', chrome)
        self.assertIn('background-color: #f0a202;\n  color: #0c040f;', gtk)

    def test_gtk3_roles(self):
        css = self.gtk3.build_css(self.colors)
        self.assertIn('headerbar,\n.titlebar:not(headerbar) {\n  background-color: #3f2c53;', css)
        self.assertIn('button:link > label {\n  color: #d2bced;', css)
        self.assertIn('background-color: #f0a202;\n  background-image: none;\n  color: #0c040f;', css)
        self.assertIn('@define-color theme_selected_bg_color #77af8a;', css)
    def test_gtk3_apply_and_clear_keep_user_css(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(self.gtk3, 'restart_portal') as portal:
            home = Path(tmp)
            state = home/'.local/state/omarchy/current'
            (state/'theme').mkdir(parents=True)
            shutil.copy2(ROOT/'colors.toml', state/'theme/colors.toml')
            (state/'theme.name').write_text('dark-r\n')
            user = home/'.config/gtk-3.0/gtk.css'
            user.parent.mkdir(parents=True)
            user.write_text('/* mine */\n')
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertIn('omarchy-dark-r.css', user.read_text())
            self.assertIn('/* mine */', user.read_text())
            self.assertTrue((home/'.config/gtk-3.0/omarchy-dark-r.css').is_file())
            (state/'theme.name').write_text('nord\n')
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertEqual(user.read_text(), '/* mine */\n')
            self.assertFalse((home/'.config/gtk-3.0/omarchy-dark-r.css').exists())
            self.assertEqual(portal.call_count, 2)
    def test_gtk3_fill_text_stays_out_of_popups(self):
        # A GTK3 menu or popover is a CSS child of the item that opened it, and
        # that item stays hovered or checked: "menuitem:hover *" made every
        # label in an open menubar menu dark on dark.
        import re
        css = self.gtk3.build_css(self.colors)
        rules = re.sub(r'/\*.*?\*/|@define-color[^;]*;', '', re.sub(r'\s+', ' ', css))
        selectors = [sel.strip() for block in re.findall(r'([^{}]+)\{', rules) for sel in block.split(',')]
        reaching = [sel for sel in selectors if re.search(r'(\s|>\s*)\*$', sel) and not sel.startswith('tooltip')]
        self.assertTrue(reaching)
        for sel in reaching:
            self.assertIn('> :not(window):not(popover) *', sel)
        self.assertIn('menuitem:hover > :not(window):not(popover),', css)
    def test_gimp_colors_cover_the_default_theme(self):
        # Every color GIMP's Default theme defines, so no gray is left over.
        css = self.gtk3.build_gimp_css(self.colors)
        names = ('fg-color', 'bg-color', 'border-color', 'dimmed-fg-color', 'disabled-fg-color',
                 'disabled-button-color', 'hover-color', 'widget-bg-color', 'selected-color',
                 'extreme-bg-color', 'extreme-selected-color', 'strong-border-color',
                 'stronger-border-color', 'edge-border-color', 'scrollbar-slider-color',
                 'scrollbar-trough-color', 'ruler-color')
        for name in names:
            self.assertRegex(css, rf'@define-color {name} +#[0-9a-f]{{6}};')
        r = self.gtk3.roles(self.colors)
        self.assertRegex(css, rf'@define-color fg-color +{r["fg"]};')
        self.assertRegex(css, rf'@define-color bg-color +{r["card"]};')
    def test_gimp_apply_and_clear_keep_user_css(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(self.gtk3, 'restart_portal'):
            home = Path(tmp)
            state = home/'.local/state/omarchy/current'
            (state/'theme').mkdir(parents=True)
            shutil.copy2(ROOT/'colors.toml', state/'theme/colors.toml')
            (state/'theme.name').write_text('dark-r\n')
            mine = home/'.config/GIMP/3.0/gimp.css'
            mine.parent.mkdir(parents=True)
            mine.write_text('/* mine */\n')
            fresh = home/'.config/GIMP/3.2/gimp.css'
            fresh.parent.mkdir(parents=True)
            (home/'.config/GIMP/2.10').mkdir()
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertTrue(mine.read_text().startswith('/* mine */\n'))
            for path in (mine, fresh):
                self.assertEqual(path.read_text().count('BEGIN omarchy-dark-r gimp'), 1)
                self.assertIn('@define-color bg-color', path.read_text())
            self.assertFalse((home/'.config/GIMP/2.10/gimp.css').exists())
            (state/'theme.name').write_text('nord\n')
            self.assertEqual(self.gtk3.apply(home), 0)
            self.assertEqual(mine.read_text(), '/* mine */\n')
            self.assertFalse(fresh.exists())

if __name__ == '__main__': unittest.main()
