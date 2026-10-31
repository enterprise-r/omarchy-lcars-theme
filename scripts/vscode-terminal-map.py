#!/usr/bin/env python3
"""Copy the current theme's Foot palette onto the VS Code terminal colors.

Omarchy fills VS Code's ANSI slots from color names. This theme's Foot palette
uses a different slot order, and Foot is the map the other terminals follow.
"""
import argparse
import re
import sys
from pathlib import Path

SLOTS = (
    ('terminal.ansiBlack', 'regular0'),
    ('terminal.ansiRed', 'regular1'),
    ('terminal.ansiGreen', 'regular2'),
    ('terminal.ansiYellow', 'regular3'),
    ('terminal.ansiBlue', 'regular4'),
    ('terminal.ansiMagenta', 'regular5'),
    ('terminal.ansiCyan', 'regular6'),
    ('terminal.ansiWhite', 'regular7'),
    ('terminal.ansiBrightBlack', 'bright0'),
    ('terminal.ansiBrightRed', 'bright1'),
    ('terminal.ansiBrightGreen', 'bright2'),
    ('terminal.ansiBrightYellow', 'bright3'),
    ('terminal.ansiBrightBlue', 'bright4'),
    ('terminal.ansiBrightMagenta', 'bright5'),
    ('terminal.ansiBrightCyan', 'bright6'),
    ('terminal.ansiBrightWhite', 'bright7'),
)

def parse_foot(text):
    section = None
    values = {}
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            continue
        if section not in ('colors-dark', 'colors') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
    return values

def hex_color(value):
    token = value.split()[0].lstrip('#')
    if len(token) != 6 or any(c not in '0123456789abcdefABCDEF' for c in token):
        raise ValueError('Expected a hex color, got ' + value)
    return '#' + token.lower()

def apply_text(vscode, foot_values):
    missing = []
    for key, foot_key in SLOTS:
        if foot_key not in foot_values:
            missing.append(foot_key)
            continue
        color = hex_color(foot_values[foot_key])
        pattern = re.compile(rf'("{re.escape(key)}"\s*:\s*")#[0-9A-Fa-f]{{6}}(")')
        vscode, count = pattern.subn(rf'\g<1>{color}\g<2>', vscode, count=1)
        if count != 1:
            missing.append(key)
    return vscode, missing

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--theme', type=Path, default=Path.home() / '.local/state/omarchy/current/theme')
    args = parser.parse_args()
    foot_path = args.theme / 'foot.ini'
    vscode_path = args.theme / 'vscode-theme.json'
    if not foot_path.is_file() or not vscode_path.is_file():
        return 0
    vscode, missing = apply_text(vscode_path.read_text(), parse_foot(foot_path.read_text()))
    if missing:
        print('VS Code terminal map was not applied: ' + ', '.join(missing), file=sys.stderr)
        return 1
    vscode_path.write_text(vscode)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
