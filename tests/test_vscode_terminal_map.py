import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vscode_terminal_map', ROOT/'scripts/vscode-terminal-map.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FOOT = """
[colors-dark]
foreground=dee5ec
background=0c040f
regular0=0c040f
regular1=ec8790
regular2=a5ace1
regular3=96c5cf
regular4=77af8a
regular5=ba9eda
regular6=f4b965
regular7=dee5ec
bright0=7b6f8b
bright1=ffa5ad
bright2=bdcbd9
bright3=cad9e7
bright4=659474
bright5=d2bced
bright6=ffd396
bright7=fff3e6
"""

THEME = """
        "terminal.ansiBlack": "#000000",
        "terminal.ansiRed": "#111111",
        "terminal.ansiGreen": "#77af8a",
        "terminal.ansiYellow": "#f4b965",
        "terminal.ansiBlue": "#a5ace1",
        "terminal.ansiCyan": "#96c5cf",
        "terminal.ansiMagenta": "#222222",
        "terminal.ansiWhite": "#333333",
        "terminal.ansiBrightBlack": "#444444",
        "terminal.ansiBrightRed": "#555555",
        "terminal.ansiBrightGreen": "#659474",
        "terminal.ansiBrightYellow": "#ffd396",
        "terminal.ansiBrightBlue": "#bdcbd9",
        "terminal.ansiBrightCyan": "#cad9e7",
        "terminal.ansiBrightMagenta": "#666666",
        "terminal.ansiBrightWhite": "#777777",
"""

class TerminalMap(unittest.TestCase):
    def test_foot_slots_replace_named_colors(self):
        text, missing = mod.apply_text(THEME, mod.parse_foot(FOOT))
        self.assertEqual(missing, [])
        self.assertIn('"terminal.ansiGreen": "#a5ace1"', text)
        self.assertIn('"terminal.ansiYellow": "#96c5cf"', text)
        self.assertIn('"terminal.ansiBlue": "#77af8a"', text)
        self.assertIn('"terminal.ansiCyan": "#f4b965"', text)
        self.assertIn('"terminal.ansiBrightGreen": "#bdcbd9"', text)
        self.assertIn('"terminal.ansiBrightYellow": "#cad9e7"', text)
        self.assertIn('"terminal.ansiBrightBlue": "#659474"', text)
        self.assertIn('"terminal.ansiBrightCyan": "#ffd396"', text)
        self.assertNotIn('#77af8a"', text.split('ansiBlue')[0])

if __name__ == '__main__':
    unittest.main()
