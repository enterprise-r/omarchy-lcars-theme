#!/usr/bin/env python3
"""Apply or clear LCARS colors for Firefox chrome.

Firefox on Linux paints toolbars from GTK system colors, not from the
libadwaita palette, so the browser stays on the default header bar. This
writes a managed userChrome.css and userContent.css into each Firefox
profile while LCARS is the active theme, and removes them otherwise.

The sheets use the named palette: card chrome, a well-colored address
field, a green current tab, amber attention, and the purple selection fill.
Firefox reads userChrome.css only after
toolkit.legacyUserProfileCustomizations.stylesheets is true, so that pref
is set in a managed user.js block. Existing user CSS and prefs stay.
"""
from __future__ import annotations

import argparse
import configparser
from pathlib import Path
import re
import tomllib

BEGIN = "/* BEGIN omarchy-lcars firefox */"
END = "/* END omarchy-lcars firefox */"
BEGIN_JS = "// BEGIN omarchy-lcars firefox"
END_JS = "// END omarchy-lcars firefox"
CHROME_IMPORT = '@import url("omarchy-lcars.css");'
CONTENT_IMPORT = '@import url("omarchy-lcars-content.css");'
CHROME_NAME = "omarchy-lcars.css"
CONTENT_NAME = "omarchy-lcars-content.css"
PREF = 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
THEME_NAME = "lcars"


def hex_ok(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def load_colors(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text())
    required = ("background", "foreground", "accent", "red", "green")
    for key in required:
        if not hex_ok(data.get(key)):
            raise ValueError(f"bad or missing color {key!r} in {path}")
    optional = (
        "lighter_background",
        "selection",
        "dark_foreground",
        "bright_foreground",
        "bright_green",
        "bright_magenta",
        "magenta",
        "hyprland_inactive_border",
        "hyprland_active_border",
    )
    out = {key: data[key] for key in required}
    for key in optional:
        if hex_ok(data.get(key)):
            out[key] = data[key]
    return out


def palette(colors: dict[str, str]) -> dict[str, str]:
    bg = colors["background"]
    fg = colors["foreground"]
    card = colors.get("lighter_background", bg)
    idle = colors.get("hyprland_inactive_border", colors.get("selection", card))
    return {
        "well": bg,
        "card": card,
        "fg": fg,
        "dim": colors.get("dark_foreground", fg),
        "focus": colors.get("bright_foreground", fg),
        "idle": idle,
        "edge": colors.get("dark_foreground", fg),
        "active": colors.get("magenta") or colors.get("hyprland_active_border") or colors["accent"],
        "selection": colors.get("selection", idle),
        "current": colors["green"],
        "current_hover": colors.get("bright_green", colors["green"]),
        "accent": colors["accent"],
        "link": colors.get("bright_magenta", colors.get("magenta", colors["accent"])),
        "danger": colors["red"],
    }


def token_block(role: dict[str, str]) -> str:
    return f"""  --toolbox-background-color: {role["card"]};
  --toolbox-background-color-inactive: {role["card"]};
  --toolbox-text-color: {role["fg"]};
  --toolbox-text-color-inactive: {role["dim"]};
  --toolbar-background-color: {role["card"]};
  --toolbar-text-color: {role["fg"]};
  --toolbar-color: {role["fg"]};
  --toolbar-field-background-color: {role["well"]};
  --toolbar-field-background-color-focus: {role["well"]};
  --toolbar-field-color: {role["fg"]};
  --toolbar-field-text-color: {role["fg"]};
  --toolbar-field-text-color-focus: {role["focus"]};
  --toolbar-field-border-color: {role["idle"]};
  --toolbar-field-border-color-focus: {role["active"]};
  --toolbar-field-focus-border-color: {role["active"]};
  --urlbar-background-color: {role["well"]};
  --urlbar-background-color-focus: {role["well"]};
  --urlbarview-background-color-selected: {role["selection"]};
  --urlbarview-text-color-selected: {role["fg"]};
  --sidebar-background-color: {role["card"]};
  --sidebar-text-color: {role["fg"]};
  --sidebar-border-color: {role["idle"]};
  --panel-background-color: {role["card"]};
  --panel-text-color: {role["fg"]};
  --panel-border-color: {role["idle"]};
  --arrowpanel-background: {role["card"]};
  --arrowpanel-color: {role["fg"]};
  --arrowpanel-border-color: {role["idle"]};
  --chrome-content-separator-color: {role["idle"]};
  --tabs-navbar-separator-color: {role["idle"]};
  --tab-background-color-hover: {role["idle"]};
  --tab-background-color-selected: {role["well"]};
  --tab-text-color-selected: {role["current"]};
  --tab-border-color-selected: {role["current"]};
  --tab-border-color-selected-leading: {role["current"]};
  --tab-border-color-selected-trailing: {role["active"]};
  --color-accent-primary: {role["current"]};
  --color-accent-primary-hover: {role["current_hover"]};
  --color-accent-primary-active: {role["current"]};
  --color-accent-attention: {role["accent"]};
  --button-background-color-primary: {role["current"]};
  --button-text-color-primary: {role["well"]};
  --button-background-color-destructive: {role["danger"]};
  --button-background-color-menu-selected: {role["selection"]};
  --button-text-color-menu-selected: {role["fg"]};
  --toolbarbutton-icon-fill-attention: {role["accent"]};
  --link-color: {role["link"]};
  --link-color-hover: {role["focus"]};
  --link-color-active: {role["focus"]};
  --focus-outline-color: {role["focus"]};
  --input-text-background-color: {role["well"]};
  --input-text-color: {role["fg"]};
  --border-color: {role["edge"]};
  --border-color-selected: {role["active"]};
  --background-color-canvas: {role["well"]};
  --background-color-box: {role["card"]};
  --background-color-list-item-hover: {role["idle"]};
  --text-color: {role["fg"]};
  accent-color: {role["current"]};"""


def build_chrome(colors: dict[str, str]) -> str:
    role = palette(colors)
    tokens = token_block(role)
    # Linux toolbars set background-color to -moz-headerbar directly, so the
    # toolbar variable alone never reaches the navigation bar.
    return f"""/* Generated by omarchy-lcars firefox-chrome. Do not edit. */
/* Palette follows the active Omarchy theme's colors.toml when LCARS is selected. */

:root {{
{tokens}
}}

toolbox,
toolbar,
#navigator-toolbox,
#nav-bar,
#TabsToolbar,
#PersonalToolbar,
#titlebar {{
  background-color: {role["card"]} !important;
  color: {role["fg"]} !important;
}}

toolbox:-moz-window-inactive,
toolbar:-moz-window-inactive,
#navigator-toolbox:-moz-window-inactive {{
  background-color: {role["card"]} !important;
  color: {role["dim"]} !important;
}}

#urlbar-input::placeholder {{
  color: {role["dim"]} !important;
  opacity: 1 !important;
}}

panel,
menupopup {{
  --panel-background-color: {role["card"]} !important;
  background-color: {role["card"]} !important;
  color: {role["fg"]} !important;
}}
"""


def build_content(colors: dict[str, str]) -> str:
    role = palette(colors)
    tokens = token_block(role)
    return f"""/* Generated by omarchy-lcars firefox-chrome. Do not edit. */

@-moz-document url-prefix("about:"), url-prefix("chrome://") {{
  :root {{
{tokens}
  }}

  :root {{
    background-color: {role["well"]};
    color: {role["fg"]};
  }}
}}
"""


def strip_block(text: str, begin: str, end: str) -> str:
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    return pattern.sub("", text)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".lcars-tmp")
    tmp.write_text(text if text.endswith("\n") else text + "\n")
    tmp.replace(path)


def write_import(path: Path, enable: bool, statement: str) -> None:
    text = path.read_text() if path.is_file() else ""
    text = strip_block(text, BEGIN, END).lstrip("\n")
    if enable:
        block = f"{BEGIN}\n{statement}\n{END}\n"
        text = block + ("\n" + text if text else "")
    if text.strip():
        write_text(path, text)
    elif path.exists() or path.is_symlink():
        path.unlink()


def write_pref(path: Path, enable: bool) -> None:
    text = path.read_text() if path.is_file() else ""
    text = strip_block(text, BEGIN_JS, END_JS).strip("\n")
    if enable:
        block = f"{BEGIN_JS}\n{PREF}\n{END_JS}"
        text = block + ("\n\n" + text if text else "")
    if text.strip():
        write_text(path, text + "\n")
    elif path.exists() or path.is_symlink():
        path.unlink()


def firefox_roots(home: Path) -> list[Path]:
    return [
        home / ".mozilla/firefox",
        home / ".var/app/org.mozilla.firefox/.mozilla/firefox",
    ]


def profiles(home: Path) -> list[Path]:
    found: list[Path] = []
    for root in firefox_roots(home):
        ini = root / "profiles.ini"
        if not ini.is_file():
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(ini)
        except configparser.Error:
            continue
        for section in parser.sections():
            if not parser.has_option(section, "Path"):
                continue
            raw = parser.get(section, "Path")
            relative = parser.get(section, "IsRelative", fallback="1") == "1"
            profile = (root / raw) if relative else Path(raw)
            if profile.is_dir() and not profile.is_symlink():
                found.append(profile)
    return found


def clear_profile(profile: Path) -> None:
    chrome = profile / "chrome"
    write_import(chrome / "userChrome.css", enable=False, statement=CHROME_IMPORT)
    write_import(chrome / "userContent.css", enable=False, statement=CONTENT_IMPORT)
    write_pref(profile / "user.js", enable=False)
    for name in (CHROME_NAME, CONTENT_NAME):
        path = chrome / name
        if path.exists() or path.is_symlink():
            path.unlink()


def paint_profile(profile: Path, chrome_css: str, content_css: str) -> None:
    chrome = profile / "chrome"
    write_text(chrome / CHROME_NAME, chrome_css)
    write_text(chrome / CONTENT_NAME, content_css)
    write_import(chrome / "userChrome.css", enable=True, statement=CHROME_IMPORT)
    write_import(chrome / "userContent.css", enable=True, statement=CONTENT_IMPORT)
    write_pref(profile / "user.js", enable=True)


def active_theme_name(home: Path) -> str:
    path = home / ".local/state/omarchy/current/theme.name"
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def apply(home: Path, colors_path: Path | None = None, force: bool = False, clear: bool = False) -> int:
    if clear:
        for profile in profiles(home):
            clear_profile(profile)
        return 0

    theme = active_theme_name(home)
    if not force and theme != THEME_NAME:
        for profile in profiles(home):
            clear_profile(profile)
        return 0

    if colors_path is None:
        colors_path = home / ".local/state/omarchy/current/theme/colors.toml"
    try:
        colors = load_colors(colors_path)
        chrome_css = build_chrome(colors)
        content_css = build_content(colors)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return 0

    for profile in profiles(home):
        paint_profile(profile, chrome_css, content_css)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove LCARS Firefox overrides")
    parser.add_argument("--force", action="store_true", help="apply even when the active theme is not LCARS")
    parser.add_argument("--colors", type=Path, help="colors.toml to render (implies --force)")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--print", action="store_true", help="print userChrome.css to stdout instead of installing")
    args = parser.parse_args()
    if args.print:
        path = args.colors or (args.home / ".local/state/omarchy/current/theme/colors.toml")
        print(build_chrome(load_colors(path)), end="")
        return 0
    force = args.force or args.colors is not None
    return apply(args.home, colors_path=args.colors, force=force, clear=args.clear)


if __name__ == "__main__":
    raise SystemExit(main())
