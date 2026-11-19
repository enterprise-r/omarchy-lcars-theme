#!/usr/bin/env python3
"""Apply or clear LCARS colors for GTK3 apps.

GTK3 themes compile their colors in, so neither Adwaita-dark (the Omarchy
default) nor Omagtk can be recolored by redefining named colors. User CSS in
~/.config/gtk-3.0/gtk.css outranks any theme by priority, so this writes a
managed sheet of color-only widget rules plus an import block, and leaves
other user CSS alone. Shapes stay the base theme's. Firefox, the GTK file
chooser portal and other GTK3 apps take their colors from here. They read
it at startup.

GIMP 3 draws its own theme over GTK3 from a set of named colors, so this
sheet alone leaves GIMP's gray panels around Dark-R buttons. The hook also
writes a managed block of those colors into each GIMP 3 profile's personal
gimp.css, which GIMP imports after its theme. GIMP reads it at startup.

When the active Omarchy theme is not LCARS, the managed import, sheet and
GIMP block are removed. Other content in gtk.css and gimp.css is preserved.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import tomllib

BEGIN = "/* BEGIN omarchy-lcars gtk3 */"
END = "/* END omarchy-lcars gtk3 */"
IMPORT = '@import url("omarchy-lcars.css");'
PALETTE_NAME = "omarchy-lcars.css"
THEME_NAME = "lcars"
GIMP_BEGIN = "/* BEGIN omarchy-lcars gimp */"
GIMP_END = "/* END omarchy-lcars gimp */"


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


def build_css(colors: dict[str, str]) -> str:
    """Widget rules for the Dark-R roles. Colors only.

    Every rule sets colors; sizes, borders, radii and shadows stay the base
    theme's. Where Adwaita draws a line with a box-shadow (focused entry,
    current tab) the rule repeats Adwaita's geometry with a palette color.
    Fills also clear background-image, since Adwaita paints buttons and bars
    with gradients.

    Text on a fill reaches the widget's own content through `inside()`. A
    GTK3 menu or popover is styled as a CSS child of the widget that opened
    it, as a `window` or `popover` node, and that widget stays hovered or
    checked while it is open. A plain descendant selector would give the
    whole popup the dark text meant for the fill.
    """
    def inside(*selectors: str) -> str:
        own = ":not(window):not(popover)"
        return ",\n".join(f"{s} > {own},\n{s} > {own} *" for s in selectors)

    r = roles(colors)
    bg, fg, card, line, edge = r["bg"], r["fg"], r["card"], r["line"], r["edge"]
    hover, on_hover = r["hover"], on_color(r["hover"], r["bg"], r["fg"])
    primary, on_primary = r["primary"], on_color(r["primary"], r["bg"], r["fg"])
    primary_hover = r["primary_hover"]
    on_primary_hover = on_color(primary_hover, r["bg"], r["fg"])
    error, on_error = r["error"], on_color(r["error"], r["bg"], r["fg"])
    error_hover = r["error_hover"]
    on_error_hover = on_color(error_hover, r["bg"], r["fg"])
    return f"""/* Generated by omarchy-lcars gtk3. Do not edit. */
/* Palette follows the active Omarchy theme's colors.toml when LCARS is selected. */

/* Names some apps look up. Themes keep their own copies. */
@define-color theme_bg_color {bg};
@define-color theme_fg_color {fg};
@define-color theme_base_color {bg};
@define-color theme_text_color {fg};
@define-color theme_selected_bg_color {primary};
@define-color theme_selected_fg_color {on_primary};
@define-color borders {edge};
@define-color link_color {r["link"]};
@define-color warning_color {r["warn"]};
@define-color error_color {error};
@define-color success_color {r["ok"]};

* {{
  outline-color: {r["focus"]};
}}

window.background,
.background,
.view,
iconview,
textview text,
list,
placesview {{
  background-color: {bg};
  color: {fg};
}}

/* Header strip, as the showcase .r-bar. */
headerbar,
.titlebar:not(headerbar) {{
  background-color: {r["bar"]};
  background-image: none;
  color: {fg};
  border-color: {edge};
}}

headerbar:backdrop,
.titlebar:not(headerbar):backdrop {{
  background-color: {card};
}}

/* Cards and panels: menus, popovers, sidebars, tooltips. */
menu,
.menu,
.context-menu,
popover,
popover.background,
tooltip.background,
.sidebar,
placessidebar,
placessidebar list,
stacksidebar,
stacksidebar list {{
  background-color: {card};
  background-image: none;
  color: {fg};
  border-color: {edge};
}}

tooltip * {{
  color: {fg};
}}

separator {{
  background-color: {line};
}}

/* Buttons: purple with a dim edge at rest, solid amber on hover, green when chosen. */
button {{
  background-color: {line};
  background-image: none;
  color: {fg};
  border-color: {edge};
}}

button:disabled {{
  background-color: {card};
  color: {r["dim"]};
  border-color: {line};
}}

/* Buttons Adwaita already draws without a fill keep none. */
button.flat,
button.titlebutton,
button.sidebar-button,
notebook > header > tabs > arrow,
modelbutton,
button:link,
button:visited {{
  background-color: transparent;
  background-image: none;
  border-color: transparent;
}}

button:hover:not(:disabled):not(:checked):not(.suggested-action):not(.destructive-action):not(:link):not(:visited),
modelbutton:hover,
menuitem:hover,
row.activatable:hover:not(:selected),
placessidebar row:hover:not(:selected),
stacksidebar row:hover:not(:selected),
notebook > header tab:hover:not(:checked) {{
  background-color: {hover};
  background-image: none;
  color: {on_hover};
  border-color: {hover};
}}

{inside(
    "button:hover:not(:disabled):not(:checked):not(.suggested-action):not(.destructive-action):not(:link):not(:visited)",
    "modelbutton:hover",
    "menuitem:hover",
    "row.activatable:hover:not(:selected)",
    "placessidebar row:hover:not(:selected)",
    "notebook > header tab:hover:not(:checked)",
)} {{
  color: {on_hover};
}}

button:checked:not(:disabled),
button.suggested-action:not(:disabled) {{
  background-color: {primary};
  background-image: none;
  color: {on_primary};
  border-color: {primary};
}}

{inside("button:checked:not(:disabled)", "button.suggested-action:not(:disabled)")} {{
  color: {on_primary};
}}

button.suggested-action:hover:not(:disabled) {{
  background-color: {primary_hover};
  border-color: {primary_hover};
  color: {on_primary_hover};
}}

/* Destructive stays red; hover brightens it. */
button.destructive-action:not(:disabled) {{
  background-color: {error};
  background-image: none;
  color: {on_error};
  border-color: {error};
}}

button.destructive-action:hover:not(:disabled) {{
  background-color: {error_hover};
  border-color: {error_hover};
  color: {on_error_hover};
}}

{inside("button.destructive-action:not(:disabled)")} {{
  color: {on_error};
}}

{inside("button.destructive-action:hover:not(:disabled)")} {{
  color: {on_error_hover};
}}

/* Fields, as the showcase inputs. */
entry {{
  background-color: {card};
  background-image: none;
  color: {fg};
  border-color: {edge};
}}

/* Adwaita's focus ring geometry, in the active-line color. */
entry:focus {{
  border-color: {r["active"]};
  box-shadow: inset 0 0 0 1px {r["active"]};
}}

entry placeholder,
.dim-label {{
  color: {r["dim"]};
}}

/* Current or chosen: green with dark text. */
row:selected,
.view:selected,
iconview:selected,
flowboxchild:selected,
calendar:selected {{
  background-color: {primary};
  color: {on_primary};
}}

{inside("row:selected", ".view:selected")} {{
  color: {on_primary};
}}

/* Text selection, as the showcase ::selection. */
selection,
entry selection,
textview text selection,
label selection {{
  background-color: {line};
  color: {r["bright"]};
}}

check,
radio {{
  border-color: {edge};
}}

check:checked,
radio:checked,
check:indeterminate,
radio:indeterminate {{
  background-color: {primary};
  background-image: none;
  color: {on_primary};
  border-color: {primary};
}}

switch {{
  background-color: {line};
  border-color: {edge};
}}

switch slider,
scale slider {{
  background-color: {r["bright"]};
  background-image: none;
  border-color: {edge};
}}

switch:checked {{
  background-color: {primary};
  border-color: {primary};
  color: {on_primary};
}}

progressbar progress,
scale highlight,
levelbar block.filled {{
  background-color: {primary};
  background-image: none;
  border-color: {primary};
}}

notebook > stack {{
  background-color: {bg};
}}

notebook > header {{
  background-color: {bg};
  background-image: none;
  border-color: {line};
}}

/* Current tab: Adwaita's 4px line, in sage. */
notebook > header tab:checked {{
  background-color: {card};
  color: {r["bright"]};
}}
notebook > header.top > tabs > tab:checked {{ box-shadow: inset 0 -4px {primary}; }}
notebook > header.bottom > tabs > tab:checked {{ box-shadow: inset 0 4px {primary}; }}
notebook > header.left > tabs > tab:checked {{ box-shadow: inset -4px 0 {primary}; }}
notebook > header.right > tabs > tab:checked {{ box-shadow: inset 4px 0 {primary}; }}

/* Adwaita colors the label inside a link button, not the button. */
*:link,
button:link,
button:link > label {{
  color: {r["link"]};
}}

*:visited,
button:visited,
button:visited > label {{
  color: {r["link_visited"]};
}}

*:link:hover,
button:link:hover,
button:link:hover > label,
button:visited:hover > label {{
  color: {r["link_hover"]};
}}

/* Notices: a card whose bottom edge, Adwaita's 1px line, carries the kind. */
infobar > revealer > box {{
  background-color: {card};
  background-image: none;
}}
infobar > revealer > box,
infobar > revealer > box label {{
  color: {fg};
}}
infobar.info > revealer > box {{ border-bottom-color: {r["info"]}; }}
infobar.question > revealer > box {{ border-bottom-color: {r["ok"]}; }}
infobar.warning > revealer > box {{ border-bottom-color: {r["warn"]}; }}
infobar.error > revealer > box {{ border-bottom-color: {error}; }}
"""


def build_gimp_css(colors: dict[str, str]) -> str:
    """GIMP's Default theme colors, from the Dark-R roles.

    GIMP keeps the foreground text on its hover and selected fills, so those
    take the quiet line color; amber and sage stay with the GTK3 sheet, which
    also reaches GIMP's buttons and lists.
    """
    r = roles(colors)
    bg, card, line, dim = r["bg"], r["card"], r["line"], r["dim"]
    names = {
        "fg-color": r["fg"],
        "bg-color": card,
        "border-color": bg,
        "dimmed-fg-color": dim,
        "disabled-fg-color": dim,
        "disabled-button-color": dim,
        "hover-color": line,
        "widget-bg-color": bg,
        "selected-color": line,
        "extreme-bg-color": bg,
        "extreme-selected-color": line,
        "strong-border-color": line,
        "stronger-border-color": line,
        "edge-border-color": bg,
        "scrollbar-slider-color": r["edge"],
        "scrollbar-trough-color": card,
        "ruler-color": bg,
    }
    width = max(map(len, names))
    lines = [f"@define-color {name:<{width}} {value};" for name, value in names.items()]
    return "/* Generated by omarchy-lcars gtk3. Do not edit inside this block. */\n" + "\n".join(lines) + "\n"


def strip_managed_block(text: str, begin: str = BEGIN, end: str = END) -> str:
    pattern = re.compile(
        re.escape(begin) + r".*?" + re.escape(end) + r"\n?",
        re.DOTALL,
    )
    return pattern.sub("", text)


def gimp_profiles(home: Path) -> list[Path]:
    """GIMP 3 profile directories, one per minor version (3.0, 3.2, ...)."""
    root = home / ".config/GIMP"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"3\.\d+", p.name))


def write_gimp(home: Path, css: str | None) -> None:
    """Put the managed block at the end of gimp.css, or take it out."""
    for profile in gimp_profiles(home):
        path = profile / "gimp.css"
        text = path.read_text() if path.is_file() else ""
        text = strip_managed_block(text, GIMP_BEGIN, GIMP_END).rstrip("\n")
        if css is not None:
            block = f"{GIMP_BEGIN}\n{css}{GIMP_END}\n"
            text = (text + "\n\n" if text else "") + block
        if text.strip():
            tmp = path.with_name(path.name + ".lcars-tmp")
            tmp.write_text(text if text.endswith("\n") else text + "\n")
            tmp.replace(path)
        elif path.exists() or path.is_symlink():
            path.unlink()


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


def active_theme_name(home: Path) -> str:
    path = home / ".local/state/omarchy/current/theme.name"
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def restart_portal() -> None:
    """The file chooser portal is a long-lived GTK3 service; it reads CSS at start."""
    subprocess.run(
        ["systemctl", "--user", "try-restart", "xdg-desktop-portal-gtk.service"],
        check=False,
        capture_output=True,
    )


def clear(home: Path) -> None:
    gtk_dir = home / ".config/gtk-3.0"
    write_import(gtk_dir / "gtk.css", enable=False)
    sheet = gtk_dir / PALETTE_NAME
    if sheet.exists() or sheet.is_symlink():
        sheet.unlink()
    write_gimp(home, None)


def apply(home: Path, colors_path: Path | None = None, force: bool = False, clear_only: bool = False) -> int:
    if clear_only or (not force and active_theme_name(home) != THEME_NAME):
        had_sheet = (home / ".config/gtk-3.0" / PALETTE_NAME).exists()
        clear(home)
        if had_sheet:
            restart_portal()
        return 0

    if colors_path is None:
        colors_path = home / ".local/state/omarchy/current/theme/colors.toml"
    try:
        colors = load_colors(colors_path)
        css = build_css(colors)
        gimp_css = build_gimp_css(colors)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return 0

    gtk_dir = home / ".config/gtk-3.0"
    gtk_dir.mkdir(parents=True, exist_ok=True)
    sheet = gtk_dir / PALETTE_NAME
    tmp = sheet.with_name(sheet.name + ".lcars-tmp")
    tmp.write_text(css)
    tmp.replace(sheet)
    write_import(gtk_dir / "gtk.css", enable=True)
    write_gimp(home, gimp_css)
    restart_portal()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove LCARS GTK3 overrides")
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
    return apply(args.home, colors_path=args.colors, force=force, clear_only=args.clear)


if __name__ == "__main__":
    raise SystemExit(main())
