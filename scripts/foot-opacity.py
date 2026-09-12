#!/usr/bin/env python3
"""Keep live Foot background alpha aligned with the selected Omarchy theme."""
import configparser
import os
from pathlib import Path
import subprocess
import tomllib

home = Path.home()
theme = home / '.local/state/omarchy/current/theme'
try:
    colors = tomllib.loads((theme / 'colors.toml').read_text())
    background = colors['background']
    if len(background) != 7 or background[0] != '#':
        raise ValueError('Expected RGB color')
    int(background[1:], 16)
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read([theme / 'foot.ini', home / '.config/foot/foot.ini'])
    alpha = config.getfloat('colors-dark', 'alpha', fallback=config.getfloat('colors', 'alpha', fallback=1.0))
    percent = round(max(0, min(1, alpha)) * 100)
except (OSError, KeyError, ValueError, configparser.Error):
    raise SystemExit(0)
sequence = ('\x1b]11;[' + str(percent) + ']' + background + '\x1b\\').encode()
result = subprocess.run(['pgrep', '-x', 'foot'], capture_output=True, text=True)
ttys = set()
for pid in result.stdout.split():
    children = subprocess.run(['pgrep', '-P', pid], capture_output=True, text=True)
    for child in children.stdout.split():
        try:
            tty = os.readlink('/proc/' + child + '/fd/1')
            if tty.startswith('/dev/pts/'):
                ttys.add(tty)
        except OSError:
            pass
for tty in ttys:
    try:
        with open(tty, 'wb', buffering=0) as output:
            output.write(sequence)
    except OSError:
        pass
