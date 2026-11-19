#!/usr/bin/env python3
"""Apply or clear LCARS colors for GTK4 / libadwaita apps.

libadwaita ignores the gtk-theme setting. The user lever it honors is
~/.config/gtk-4.0/gtk.css. This writes a managed palette file and an import
block so LCARS can leave any other user CSS alone.

When the active Omarchy theme is not LCARS, the managed import and palette
file are removed. Existing non-LCARS content in gtk.css is preserved.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tomllib

BEGIN = "/* BEGIN omarchy-lcars gtk4 */"
END = "/* END omarchy-lcars gtk4 */"
IMPORT = '@import url("omarchy-lcars.css");'
PALETTE_NAME = "omarchy-lcars.css"
THEME_NAME = "lcars"

# D-Bus activatable services that keep a process alive after the window closes.
# libadwaita loads user CSS at startup, so they need a restart to repaint.
RESTART_NAMES = (
    "nautilus",
    "geary",
    "gnome-calendar",
    "gnome-control-center",
    "gnome-system-monitor",
    "baobab",
    "evince",
    "loupe",
    "simple-scan",
)


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


def ink(color: str, background: str, bright: str | None = None) -> str:
    """Palette color for icons and text on the window.

    libadwaita's documented standalone form lightens with
    `oklab(... max(l, 0.85) ...)`, which can paint a color the palette does
    not contain. Use the palette color when it already reads on the
    background.
    """
    if contrast(color, background) >= 4.5:
        return color
    if bright and contrast(bright, background) >= 4.5:
        return bright
    return on_color(background, background, color)


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


def build_css(colors: dict[str, str]) -> str:
    r = roles(colors)
    bg, fg, card = r["bg"], r["fg"], r["card"]

    def tone(name: str) -> tuple[str, str, str]:
        # Standalone ink, filled background, text on the fill.
        fill = r[name]
        return ink(fill, bg), fill, on_color(fill, bg, fg)

    accent_ink, accent_bg, accent_fg = tone("primary")
    error_ink, error_bg, error_fg = tone("error")
    ok_ink, ok_bg, ok_fg = tone("ok")
    warn_ink, warn_bg, warn_fg = tone("warn")

    # libadwaita 1.10 defines each --var from the matching @define-color, and
    # older releases read only the latter, so one table feeds both forms.
    adwaita = {
        "window_bg_color": bg,
        "window_fg_color": fg,
        "view_bg_color": bg,
        "view_fg_color": fg,
        "headerbar_bg_color": r["bar"],
        "headerbar_fg_color": fg,
        "headerbar_border_color": r["edge"],
        "headerbar_backdrop_color": card,
        "card_bg_color": card,
        "card_fg_color": fg,
        "dialog_bg_color": card,
        "dialog_fg_color": fg,
        "popover_bg_color": card,
        "popover_fg_color": fg,
        "sidebar_bg_color": card,
        "sidebar_fg_color": fg,
        "sidebar_backdrop_color": bg,
        "sidebar_border_color": r["edge"],
        "secondary_sidebar_bg_color": card,
        "secondary_sidebar_fg_color": fg,
        "secondary_sidebar_backdrop_color": bg,
        "secondary_sidebar_border_color": r["edge"],
        "thumbnail_bg_color": card,
        "thumbnail_fg_color": fg,
        "overview_bg_color": card,
        "overview_fg_color": fg,
        "accent_color": accent_ink,
        "accent_bg_color": accent_bg,
        "accent_fg_color": accent_fg,
        "destructive_color": error_ink,
        "destructive_bg_color": error_bg,
        "destructive_fg_color": error_fg,
        "success_color": ok_ink,
        "success_bg_color": ok_bg,
        "success_fg_color": ok_fg,
        "warning_color": warn_ink,
        "warning_bg_color": warn_bg,
        "warning_fg_color": warn_fg,
        "error_color": error_ink,
        "error_bg_color": error_bg,
        "error_fg_color": error_fg,
    }
    # GTK3-era names that some GTK4 apps still read.
    legacy = {
        "theme_bg_color": bg,
        "theme_fg_color": fg,
        "theme_base_color": bg,
        "theme_text_color": fg,
        "theme_selected_bg_color": r["line"],
        "theme_selected_fg_color": r["bright"],
        "theme_unfocused_bg_color": bg,
        "theme_unfocused_fg_color": fg,
        "theme_unfocused_base_color": bg,
        "theme_unfocused_text_color": fg,
        "theme_unfocused_selected_bg_color": r["line"],
        "theme_unfocused_selected_fg_color": r["bright"],
        "insensitive_bg_color": bg,
        "insensitive_fg_color": r["dim"],
        "insensitive_base_color": bg,
        "borders": r["edge"],
        "unfocused_borders": r["edge"],
        "link_color": r["link"],
        "unfocused_insensitive_color": r["dim"],
    }

    lines = [
        "/* Generated by omarchy-lcars gtk4-libadwaita. Do not edit. */",
        "/* Palette follows the active Omarchy theme's colors.toml when LCARS is selected. */",
        "",
    ]
    for name, value in {**adwaita, **legacy}.items():
        lines.append(f"@define-color {name} {value};")
    lines.append("")
    # :root covers modern libadwaita; window covers cases where root scope is inert.
    for selector in (":root", "window", "window.background"):
        lines.append(f"{selector} {{")
        for name, value in adwaita.items():
            lines.append(f"  --{name.replace('_', '-')}: {value};")
        lines.append("}")
        lines.append("")
    lines.append(widget_rules(r))
    return "\n".join(lines).rstrip() + "\n"


def widget_rules(r: dict[str, str]) -> str:
    """States libadwaita paints from currentColor washes or the accent.

    User CSS outranks the theme by priority, so plain selectors win. A wash
    of the light text over the dark window reads as gray, and libadwaita has
    one accent for checked controls, links, focus and selection, so these
    few rules carry the Dark-R roles that the variables cannot. They set
    colors only; shapes stay libadwaita's.
    """
    on_hover = on_color(r["hover"], r["bg"], r["fg"])
    on_primary = on_color(r["primary"], r["bg"], r["fg"])
    on_primary_hover = on_color(r["primary_hover"], r["bg"], r["fg"])
    on_error_hover = on_color(r["error_hover"], r["bg"], r["fg"])
    return f"""/* Header strip, as the showcase .r-bar. */
toolbarview > .top-bar,
toolbarview > .top-bar headerbar {{
  background-color: {r["bar"]};
}}

/* Hover: solid amber with dark text, as the launcher. */
button:hover:not(:disabled):not(:checked):not(.suggested-action):not(.destructive-action):not(.link),
modelbutton:hover,
.navigation-sidebar > row:hover:not(:selected) {{
  background-color: {r["hover"]};
  color: {on_hover};
}}

/* Current or chosen: green with dark text. */
button:checked:not(.suggested-action):not(.destructive-action),
.navigation-sidebar > row:selected {{
  background-color: {r["primary"]};
  color: {on_primary};
}}

/* Suggested and destructive keep their color on hover, brightened. */
button.suggested-action:hover:not(:disabled) {{
  background-color: {r["primary_hover"]};
  color: {on_primary_hover};
}}

button.destructive-action:hover:not(:disabled) {{
  background-color: {r["error_hover"]};
  color: {on_error_hover};
}}

selection,
text selection {{
  background-color: {r["line"]};
  color: {r["bright"]};
}}

link,
button.link {{
  color: {r["link"]};
}}

link:visited,
button.link:visited {{
  color: {r["link_visited"]};
}}

link:hover,
button.link:hover {{
  color: {r["link_hover"]};
}}

:focus-visible {{
  outline-color: {r["focus"]};
}}
"""


def strip_managed_block(text: str) -> str:
    pattern = re.compile(
        re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
        re.DOTALL,
    )
    return pattern.sub("", text)


def write_import(gtk_css: Path, enable: bool) -> None:
    text = gtk_css.read_text() if gtk_css.is_file() else ""
    text = strip_managed_block(text).lstrip("\n")
    if enable:
        block = f"{BEGIN}\n{IMPORT}\n{END}\n"
        text = block + ("\n" + text if text else "")
    if text.strip():
        gtk_css.parent.mkdir(parents=True, exist_ok=True)
        tmp = gtk_css.with_name(gtk_css.name + ".lcars-tmp")
        tmp.write_text(text if text.endswith("\n") else text + "\n")
        tmp.replace(gtk_css)
    elif gtk_css.exists() or gtk_css.is_symlink():
        gtk_css.unlink()


def restart_gtk_services() -> None:
    for name in RESTART_NAMES:
        subprocess.run(["pkill", "-x", "-TERM", name], check=False, capture_output=True)


def active_theme_name(home: Path) -> str:
    path = home / ".local/state/omarchy/current/theme.name"
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def apply(home: Path, colors_path: Path | None = None, force: bool = False, clear: bool = False) -> int:
    gtk_dir = home / ".config/gtk-4.0"
    palette = gtk_dir / PALETTE_NAME
    gtk_css = gtk_dir / "gtk.css"

    if clear:
        write_import(gtk_css, enable=False)
        if palette.exists() or palette.is_symlink():
            palette.unlink()
        restart_gtk_services()
        return 0

    theme = active_theme_name(home)
    if not force and theme != THEME_NAME:
        write_import(gtk_css, enable=False)
        if palette.exists() or palette.is_symlink():
            palette.unlink()
        return 0

    if colors_path is None:
        colors_path = home / ".local/state/omarchy/current/theme/colors.toml"
    try:
        colors = load_colors(colors_path)
        css = build_css(colors)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return 0

    gtk_dir.mkdir(parents=True, exist_ok=True)
    tmp = palette.with_name(palette.name + ".lcars-tmp")
    tmp.write_text(css)
    tmp.replace(palette)
    write_import(gtk_css, enable=True)
    restart_gtk_services()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove LCARS GTK4 overrides")
    parser.add_argument("--force", action="store_true", help="apply even when the active theme is not LCARS")
    parser.add_argument("--colors", type=Path, help="colors.toml to render (implies --force)")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--print", action="store_true", help="print CSS to stdout instead of installing")
    args = parser.parse_args()
    if args.print:
        path = args.colors or (args.home / ".local/state/omarchy/current/theme/colors.toml")
        print(build_css(load_colors(path)), end="")
        return 0
    force = args.force or args.colors is not None
    return apply(args.home, colors_path=args.colors, force=force, clear=args.clear)


if __name__ == "__main__":
    raise SystemExit(main())
