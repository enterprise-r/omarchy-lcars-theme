#!/usr/bin/env python3
"""Apply or clear LCARS colors for Firefox chrome.

Firefox on Linux paints toolbars from GTK system colors, not from the
libadwaita palette, so the browser stays on the default header bar. Current
Firefox also keeps its profiles under ~/.config/mozilla/firefox. This writes
a managed userChrome.css and userContent.css into each browsing profile
while LCARS is the active theme, and removes them otherwise. The WebApps
profile is left alone; that chrome is hidden on purpose.

The sheets set named Firefox tokens on :root, plus two hover rules Firefox
does not expose as tokens. Colors come from the same Dark-R roles as the
GTK4 hook, so the toolbar matches the libadwaita header bar and menus match
popovers. Declarations are !important because Firefox loads these as user
sheets, which lose to its own rules for the native GTK theme.
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


def luminance(color: str) -> float:
    """WCAG relative luminance."""
    def channel(i: int) -> float:
        c = int(color[i:i + 2], 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def on_color(surface: str, background: str, foreground: str) -> str:
    """Readable text on a filled surface, preferring the theme's own colors."""
    best = foreground
    best_ratio = 0.0
    for candidate in (background, foreground, "#ffffff", "#000000"):
        ratio = contrast(surface, candidate)
        if candidate in ("#ffffff", "#000000") and best_ratio >= 4.5:
            continue
        if ratio > best_ratio:
            best = candidate
            best_ratio = ratio
    return best


# ROLES-BEGIN: keep identical in gtk3.py, gtk4-libadwaita.py, firefox-chrome.py
# and vscode-surfaces.py.
REQUIRED = ("background", "foreground", "accent", "red", "green")
OPTIONAL = (
    "lighter_background",
    "selection",
    "dark_foreground",
    "bright_foreground",
    "yellow",
    "blue",
    "magenta",
    "bright_red",
    "bright_yellow",
    "bright_green",
    "bright_magenta",
    "hyprland_inactive_border",
    "hyprland_active_border",
)


def load_colors(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text())
    for key in REQUIRED:
        if not hex_ok(data.get(key)):
            raise ValueError(f"bad or missing color {key!r} in {path}")
    out = {key: data[key] for key in REQUIRED}
    for key in OPTIONAL:
        if hex_ok(data.get(key)):
            out[key] = data[key]
    return out


def roles(colors: dict[str, str]) -> dict[str, str]:
    """Dark-R UI roles (enterprise-r.com/showcase) from colors.toml.

    bar      --ui-border: header bars and the browser toolbar (.r-bar)
    line     --ui-border: text selection, quiet separators
    edge     --ui-fg-dark: card, panel and field borders
    hover    --ui-accent: pointer and keyboard cursor
    primary  --ui-green: current, chosen, checked, suggested, selected tab
    focus    --ui-fg-bright: keyboard focus ring
    active   --ui-border-active: focused field
    link     --ui-magenta-bright, hover yellow-bright, visited yellow
    notices  info blue, ok green, warn accent, error red
    destructive buttons stay red; hover brightens them, as primary
    """
    bg = colors["background"]
    fg = colors["foreground"]
    accent = colors["accent"]
    green = colors["green"]
    card = colors.get("lighter_background", bg)
    line = colors.get("hyprland_inactive_border", colors.get("selection", card))
    magenta = colors.get("magenta", accent)
    return {
        "bg": bg,
        "fg": fg,
        "card": card,
        "bar": line,
        "line": line,
        "edge": colors.get("dark_foreground", fg),
        "dim": colors.get("dark_foreground", fg),
        "bright": colors.get("bright_foreground", fg),
        "hover": accent,
        "primary": green,
        "primary_hover": colors.get("bright_green", green),
        "focus": colors.get("bright_foreground", fg),
        "active": colors.get("hyprland_active_border", magenta),
        "link": colors.get("bright_magenta", magenta),
        "link_hover": colors.get("bright_yellow", accent),
        "link_visited": colors.get("yellow", magenta),
        "info": colors.get("blue", accent),
        "ok": green,
        "warn": accent,
        "error": colors["red"],
        "error_hover": colors.get("bright_red", colors["red"]),
    }
# ROLES-END


def shared_tokens(r: dict[str, str]) -> dict[str, str]:
    """Tokens that chrome and about: pages both read.

    Hover is a solid amber fill with dark text, as in the launcher. A
    translucent amber over the dark surfaces reads as brown, and Firefox's
    own currentColor washes read as gray, so neither is used.
    """
    on_hover = on_color(r["hover"], r["bg"], r["fg"])
    on_primary = on_color(r["primary"], r["bg"], r["fg"])
    on_error = on_color(r["error"], r["bg"], r["fg"])
    on_error_hover = on_color(r["error_hover"], r["bg"], r["fg"])
    return {
        "--color-accent-primary": r["primary"],
        "--color-accent-primary-hover": r["primary_hover"],
        "--color-accent-primary-active": r["primary_hover"],
        # --button-text-color is also the text of panel menus, so it stays
        # light and plain buttons take a dark fill.
        "--button-background-color": r["line"],
        "--button-background-color-hover": r["hover"],
        "--button-background-color-active": r["hover"],
        "--button-text-color-hover": on_hover,
        "--button-text-color-active": on_hover,
        "--button-border-color": "transparent",
        "--button-background-color-ghost": "transparent",
        "--button-background-color-ghost-hover": r["hover"],
        "--button-background-color-ghost-active": r["hover"],
        "--button-text-color-ghost-hover": on_hover,
        "--button-text-color-ghost-active": on_hover,
        "--button-background-color-menu-hover": r["hover"],
        "--button-background-color-menu-active": r["hover"],
        "--button-text-color-menu-hover": on_hover,
        "--button-text-color-menu-active": on_hover,
        "--button-background-color-primary": r["primary"],
        "--button-background-color-primary-hover": r["primary_hover"],
        "--button-background-color-primary-active": r["primary_hover"],
        "--button-text-color-primary": on_primary,
        "--button-text-color-primary-hover": on_primary,
        "--button-text-color-primary-active": on_primary,
        "--button-background-color-destructive": r["error"],
        # Destructive stays red; hover brightens it, as primary does.
        "--button-background-color-destructive-hover": r["error_hover"],
        "--button-background-color-destructive-active": r["error_hover"],
        "--button-text-color-destructive": on_error,
        "--button-text-color-destructive-hover": on_error_hover,
        "--button-text-color-destructive-active": on_error_hover,
        "--background-color-list-item-hover": r["hover"],
        "--text-color-list-item-hover": on_hover,
        "--background-color-dimmed": r["line"],
        "--background-color-dimmed-further": r["line"],
        # Notices are cards; the icon carries the kind (.r-notice).
        "--background-color-information": r["card"],
        "--background-color-success": r["card"],
        "--background-color-warning": r["card"],
        "--background-color-critical": r["card"],
        "--card-border-color": r["edge"],
        "--focus-outline-color": r["focus"],
        "--link-color": r["link"],
        "--link-color-hover": r["link_hover"],
        "--link-color-active": r["link_hover"],
        "--link-color-visited": r["link_visited"],
        "--icon-color-information": r["info"],
        "--icon-color-success": r["ok"],
        "--icon-color-warning": r["warn"],
        "--icon-color-critical": r["error"],
        "--text-color-error": r["error"],
        "accent-color": r["primary"],
    }


def chrome_tokens(r: dict[str, str]) -> dict[str, str]:
    """Browser chrome. Matches the libadwaita header bar and popovers."""
    on_hover = on_color(r["hover"], r["bg"], r["fg"])
    return {
        "--toolbox-background-color": r["bar"],
        "--toolbox-background-color-inactive": r["card"],
        "--toolbox-text-color": r["fg"],
        "--toolbox-text-color-inactive": r["fg"],
        "--toolbar-background-color": r["bar"],
        "--toolbar-text-color": r["fg"],
        "--toolbar-field-background-color": r["card"],
        "--toolbar-field-background-color-focus": r["card"],
        "--toolbar-field-text-color": r["fg"],
        "--toolbar-field-text-color-focus": r["fg"],
        "--toolbar-field-border-color": r["edge"],
        "--toolbar-field-border-color-focus": r["active"],
        "--toolbarbutton-icon-fill": r["fg"],
        "--toolbarbutton-icon-fill-attention": r["warn"],
        "--toolbarbutton-background-color-hover": r["hover"],
        "--toolbarbutton-background-color-active": r["hover"],
        "--urlbar-box-background-color": "transparent",
        "--urlbar-box-text-color-hover": on_hover,
        "--tab-background-color-hover": r["hover"],
        "--tab-text-color-hover": on_hover,
        "--tab-background-color-selected": r["card"],
        "--tab-text-color-selected": r["bright"],
        "--tab-border-color-selected": r["primary"],
        # Firefox's newer tab style (browser.nova.enabled, on by default
        # since 158) outlines the selected tab with a violet-to-orange
        # gradient from these two; both ends sage makes it the current mark.
        "--tab-border-color-selected-leading": r["primary"],
        "--tab-border-color-selected-trailing": r["primary"],
        "--sidebar-background-color": r["card"],
        "--sidebar-text-color": r["fg"],
        "--sidebar-border-color": r["edge"],
        "--panel-background-color": r["card"],
        "--panel-text-color": r["fg"],
        "--panel-border-color": r["edge"],
        "--panel-separator-color": r["line"],
        # The address bar list is a launcher: the keyboard row is the hover fill.
        "--urlbarview-background-color-selected": r["hover"],
        "--urlbarview-text-color-selected": on_hover,
        **shared_tokens(r),
    }


def chrome_rules(r: dict[str, str]) -> str:
    """The two hover states Firefox paints from fixed colors, not tokens."""
    on_hover = on_color(r["hover"], r["bg"], r["fg"])
    return f"""/* Toolbar icons keep their fill on hover outside high-contrast mode. */
toolbar .toolbarbutton-1:not([disabled]):is(:hover, [open], [checked]) {{
  fill: {on_hover} !important;
  color: {on_hover} !important;
}}

/* Context menus hover with the GTK theme's -moz-menuhover. */
menupopup > :is(menu, menuitem)[_moz-menuactive]:not([disabled]) {{
  background-color: {r["hover"]} !important;
  color: {on_hover} !important;
}}
"""


def content_tokens(r: dict[str, str]) -> dict[str, str]:
    """about: pages. Page, cards and fields as on the showcase."""
    return {
        "--background-color-canvas": r["bg"],
        "--background-color-box": r["card"],
        "--text-color": r["fg"],
        "--text-color-deemphasized": r["dim"],
        "--border-color": r["edge"],
        **shared_tokens(r),
    }


def declarations(tokens: dict[str, str], indent: str) -> str:
    # Firefox loads these as user sheets. Its own :root rules for the native
    # GTK theme are author rules, which beat normal user declarations.
    return "\n".join(f"{indent}{name}: {value} !important;" for name, value in tokens.items())


def build_chrome(colors: dict[str, str]) -> str:
    r = roles(colors)
    return f"""/* Generated by omarchy-lcars firefox-chrome. Do not edit. */
/* Palette follows the active Omarchy theme's colors.toml when LCARS is selected. */

:root {{
{declarations(chrome_tokens(r), "  ")}
}}

{chrome_rules(r)}"""


def build_content(colors: dict[str, str]) -> str:
    return f"""/* Generated by omarchy-lcars firefox-chrome. Do not edit. */

@-moz-document url-prefix("about:"), url-prefix("chrome://") {{
  :root {{
{declarations(content_tokens(roles(colors)), "    ")}
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
    # Firefox 144+ uses the XDG config dir when ~/.mozilla was never created.
    return [
        home / ".config/mozilla/firefox",
        home / ".mozilla/firefox",
        home / ".var/app/org.mozilla.firefox/.config/mozilla/firefox",
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
            # The webapp profile hides the toolbar. Recoloring it fights that.
            if parser.get(section, "Name", fallback="") == "WebApps":
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
