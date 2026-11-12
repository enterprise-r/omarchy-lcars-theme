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


def luma(color: str) -> float:
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luma(a), luma(b)
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


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, round(r))),
        max(0, min(255, round(g))),
        max(0, min(255, round(b))),
    )


def mix(a: str, b: str, t: float) -> str:
    """Mix `t` of `b` into `a`. Both arguments are #rrggbb."""
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return _hex(ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t)


def scale(color: str, factor: float) -> str:
    """Lighten or darken without shifting the hue toward gray."""
    r, g, b = _rgb(color)
    return _hex(r * factor, g * factor, b * factor)


def lift(color: str, foreground: str, factor: float, fallback: float) -> str:
    """Raise a surface. Scale first so a purple window stays purple.

    Mixing the neutral foreground in washes this palette out to gray. Fall
    back to that mix only when the background is too close to black to scale.
    """
    lifted = scale(color, factor)
    if sum(abs(a - b) for a, b in zip(_rgb(color), _rgb(lifted))) < 16:
        return mix(color, foreground, fallback)
    return lifted


def ink(color: str, background: str, bright: str | None = None) -> str:
    """Palette color for icons and text on the window.

    libadwaita's documented standalone form lightens with
    `oklab(... max(l, 0.85) ...)`. On this gold that leaves sRGB, so links
    and accent icons paint a color the palette does not contain. Use the
    palette color when it already reads on the background.
    """
    if contrast(color, background) >= 4.5:
        return color
    if bright and contrast(bright, background) >= 4.5:
        return bright
    return on_color(background, background, color)


def load_colors(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text())
    required = ("background", "foreground", "accent", "red", "green", "yellow")
    for key in required:
        if not hex_ok(data.get(key)):
            raise ValueError(f"bad or missing color {key!r} in {path}")
    optional = (
        "dark_background",
        "darker_background",
        "lighter_background",
        "selection",
        "blue",
        "cyan",
        "magenta",
        "orange",
        "bright_foreground",
        "bright_yellow",
        "bright_orange",
        "bright_red",
        "bright_green",
        "bright_blue",
        "bright_cyan",
        "bright_magenta",
    )
    out = {key: data[key] for key in required}
    for key in optional:
        if hex_ok(data.get(key)):
            out[key] = data[key]
    return out


def build_css(colors: dict[str, str]) -> str:
    bg = colors["background"]
    fg = colors["foreground"]
    accent = colors["accent"]
    red = colors["red"]
    green = colors["green"]
    yellow = colors["yellow"]
    # Terminal slots such as lighter_background (#181820) and selection
    # (#41285b) are a different hue from the window. Scale the background
    # instead so header bars, cards, and sidebars stay in its family.
    dark = luma(bg) <= luma(fg)
    if dark:
        view = scale(bg, 0.62)
        secondary = lift(bg, fg, 1.45, 0.04)
        sidebar = lift(bg, fg, 1.85, 0.07)
        card = lift(bg, fg, 2.2, 0.09)
        header = lift(bg, fg, 2.55, 0.11)
        popover = lift(bg, fg, 3.3, 0.16)
    else:
        view = mix(bg, "#ffffff", 0.28)
        secondary = mix(bg, fg, 0.04)
        sidebar = mix(bg, fg, 0.07)
        card = mix(bg, fg, 0.09)
        header = mix(bg, fg, 0.11)
        popover = mix(bg, fg, 0.16)
    border = colors.get("blue", fg)

    accent_ink = ink(accent, bg, colors.get("bright_yellow") or colors.get("orange"))
    red_ink = ink(red, bg, colors.get("bright_red"))
    green_ink = ink(green, bg, colors.get("bright_green"))
    yellow_ink = ink(yellow, bg, colors.get("bright_yellow"))

    accent_fg = on_color(accent, bg, fg)
    red_fg = on_color(red, bg, fg)
    green_fg = on_color(green, bg, fg)
    yellow_fg = on_color(yellow, bg, fg)

    # Both @define-color (older libadwaita / some GTK4 CSS) and --vars (1.6+).
    named = {
        "window_bg_color": bg,
        "window_fg_color": fg,
        "view_bg_color": view,
        "view_fg_color": fg,
        "headerbar_bg_color": header,
        "headerbar_fg_color": fg,
        "headerbar_border_color": border,
        "headerbar_backdrop_color": bg,
        "headerbar_shade_color": "alpha(black, 0.36)",
        "headerbar_darker_shade_color": f"alpha({border}, 0.55)",
        "card_bg_color": card,
        "card_fg_color": fg,
        "card_shade_color": "alpha(black, 0.36)",
        "dialog_bg_color": popover,
        "dialog_fg_color": fg,
        "popover_bg_color": popover,
        "popover_fg_color": fg,
        "popover_shade_color": "alpha(black, 0.36)",
        "sidebar_bg_color": sidebar,
        "sidebar_fg_color": fg,
        "sidebar_backdrop_color": bg,
        "sidebar_border_color": border,
        "sidebar_shade_color": "alpha(black, 0.25)",
        "secondary_sidebar_bg_color": secondary,
        "secondary_sidebar_fg_color": fg,
        "secondary_sidebar_backdrop_color": bg,
        "secondary_sidebar_border_color": border,
        "secondary_sidebar_shade_color": "alpha(black, 0.25)",
        "thumbnail_bg_color": popover,
        "thumbnail_fg_color": fg,
        "accent_color": accent_ink,
        "accent_bg_color": accent,
        "accent_fg_color": accent_fg,
        "destructive_color": red_ink,
        "destructive_bg_color": red,
        "destructive_fg_color": red_fg,
        "success_color": green_ink,
        "success_bg_color": green,
        "success_fg_color": green_fg,
        "warning_color": yellow_ink,
        "warning_bg_color": yellow,
        "warning_fg_color": yellow_fg,
        "error_color": red_ink,
        "error_bg_color": red,
        "error_fg_color": red_fg,
        "theme_bg_color": bg,
        "theme_fg_color": fg,
        "theme_base_color": view,
        "theme_text_color": fg,
        "theme_selected_bg_color": accent,
        "theme_selected_fg_color": accent_fg,
        "theme_unfocused_bg_color": bg,
        "theme_unfocused_fg_color": fg,
        "theme_unfocused_base_color": view,
        "theme_unfocused_text_color": fg,
        "theme_unfocused_selected_bg_color": accent,
        "theme_unfocused_selected_fg_color": accent_fg,
        "insensitive_bg_color": bg,
        "insensitive_fg_color": f"alpha({fg}, 0.5)",
        "insensitive_base_color": view,
        # Finished border color. The headerbar variable stays opaque because
        # libadwaita mixes it with --border-opacity itself.
        "borders": f"alpha({border}, 0.4)",
        "unfocused_borders": f"alpha({border}, 0.28)",
        "link_color": accent_ink,
        "unfocused_insensitive_color": f"alpha({fg}, 0.5)",
    }

    vars_map = {
        "--window-bg-color": bg,
        "--window-fg-color": fg,
        "--view-bg-color": view,
        "--view-fg-color": fg,
        "--headerbar-bg-color": header,
        "--headerbar-fg-color": fg,
        "--headerbar-border-color": border,
        "--headerbar-backdrop-color": bg,
        "--headerbar-shade-color": "rgb(0 0 0 / 36%)",
        "--headerbar-darker-shade-color": f"color-mix(in srgb, {border} 55%, transparent)",
        "--card-bg-color": card,
        "--card-fg-color": fg,
        "--card-shade-color": "rgb(0 0 0 / 36%)",
        "--dialog-bg-color": popover,
        "--dialog-fg-color": fg,
        "--popover-bg-color": popover,
        "--popover-fg-color": fg,
        "--popover-shade-color": "rgb(0 0 0 / 36%)",
        "--sidebar-bg-color": sidebar,
        "--sidebar-fg-color": fg,
        "--sidebar-backdrop-color": bg,
        "--sidebar-border-color": border,
        "--sidebar-shade-color": "rgb(0 0 0 / 25%)",
        "--secondary-sidebar-bg-color": secondary,
        "--secondary-sidebar-fg-color": fg,
        "--secondary-sidebar-backdrop-color": bg,
        "--secondary-sidebar-border-color": border,
        "--secondary-sidebar-shade-color": "rgb(0 0 0 / 25%)",
        "--thumbnail-bg-color": popover,
        "--thumbnail-fg-color": fg,
        "--overview-bg-color": popover,
        "--overview-fg-color": fg,
        "--accent-bg-color": accent,
        "--accent-fg-color": accent_fg,
        "--accent-color": accent_ink,
        "--destructive-bg-color": red,
        "--destructive-fg-color": red_fg,
        "--destructive-color": red_ink,
        "--success-bg-color": green,
        "--success-fg-color": green_fg,
        "--success-color": green_ink,
        "--warning-bg-color": yellow,
        "--warning-fg-color": yellow_fg,
        "--warning-color": yellow_ink,
        "--error-bg-color": red,
        "--error-fg-color": red_fg,
        "--error-color": red_ink,
        "--shade-color": "rgb(0 0 6 / 25%)",
        "--scrollbar-outline-color": "rgb(0 0 6 / 50%)",
    }

    lines = [
        "/* Generated by omarchy-lcars gtk4-libadwaita. Do not edit. */",
        "/* Palette follows the active Omarchy theme's colors.toml when LCARS is selected. */",
        "",
    ]
    for name, value in named.items():
        lines.append(f"@define-color {name} {value};")
    lines.append("")
    # :root covers modern libadwaita; window covers cases where root scope is inert.
    for selector in (":root", "window", "window.background"):
        lines.append(f"{selector} {{")
        for name, value in vars_map.items():
            lines.append(f"  {name}: {value};")
        lines.append("}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
