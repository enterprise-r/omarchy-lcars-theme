#!/usr/bin/env python3
"""Separate VS Code chrome into a few surface steps.

Omarchy's generated theme paints the activity bar, sidebar, editor, panel,
and title bar with one background, so they read as a single slab. Catppuccin
keeps those roles apart: a deep frame, a mid sidebar, a lighter field for
inputs and popups, and the editor as its own surface.

LCARS syntax colors are tuned for the near-black editor, so the code well
stays `background`. The surrounding chrome steps up through
`lighter_background` the way Catppuccin steps mantle, base, and surface0.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tomllib

THEME_NAME = "lcars"
THEME_FILE = "vscode-theme.json"


def hex_ok(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, round(r))),
        max(0, min(255, round(g))),
        max(0, min(255, round(b))),
    )


def mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return _hex(ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t)


def scale(color: str, factor: float) -> str:
    r, g, b = _rgb(color)
    return _hex(r * factor, g * factor, b * factor)


def luma(color: str) -> float:
    r, g, b = _rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    dark, light = sorted((luma(a), luma(b)))
    return (light + 0.05) / (dark + 0.05)


def scale_to_luma(color: str, target: float) -> str:
    current = luma(color)
    if current <= 0.01:
        return color
    return scale(color, target / current)


def hold_contrast(surface: str, ink: str, anchor: str, minimum: float) -> str:
    """Darken `surface` toward `anchor` until `ink` can be read on it."""
    for _ in range(8):
        if contrast(surface, ink) >= minimum:
            return surface
        surface = mix(surface, anchor, 0.18)
    return surface


def load_colors(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text())
    required = ("background", "foreground", "accent")
    for key in required:
        if not hex_ok(data.get(key)):
            raise ValueError(f"bad or missing color {key!r} in {path}")
    optional = (
        "lighter_background",
        "selection",
        "blue",
        "muted",
        "light_foreground",
        "dark_foreground",
    )
    out = {key: data[key] for key in required}
    for key in optional:
        if hex_ok(data.get(key)):
            out[key] = data[key]
    return out


def surfaces(colors: dict[str, str]) -> dict[str, str] | None:
    """Catppuccin-style roles, kept in this palette's purple-black hue.

    The editor stays on `background`. Sidebar uses `lighter_background` when
    that step is actually lighter. Frame, fields, and the panel sit on either
    side of the sidebar so each region has its own fill.
    """
    editor = colors["background"]
    foreground = colors["foreground"]
    if luma(editor) > luma(foreground):
        return None

    mantle = colors.get("lighter_background", "")
    if not hex_ok(mantle) or luma(mantle) < luma(editor) + 10:
        mantle = scale_to_luma(mix(editor, "#c8c0d4", 0.22), luma(editor) + 16)

    frame = scale_to_luma(mantle, min(luma(mantle) + 12, 36))
    frame = hold_contrast(frame, colors["accent"], editor, 4.5)
    field = scale_to_luma(mantle, min(max(luma(frame) + 10, luma(mantle) + 18), 46))
    field = hold_contrast(field, foreground, editor, 4.5)
    panel = mix(editor, mantle, 0.45)

    selection = colors.get("selection", "")
    if not hex_ok(selection) or contrast(selection, foreground) < 4.5:
        selection = field

    return {
        "editor": editor,
        "panel": panel,
        "sidebar": mantle,
        "frame": frame,
        "field": field,
        "selection": selection,
        "rule": colors.get("blue", colors["accent"]),
        "accent": colors["accent"],
        "foreground": foreground,
        "placeholder": colors.get("light_foreground", foreground),
    }


def chrome(colors: dict[str, str]) -> dict[str, str]:
    role = surfaces(colors)
    if role is None:
        return {}
    editor = role["editor"]
    panel = role["panel"]
    sidebar = role["sidebar"]
    frame = role["frame"]
    field = role["field"]
    selection = role["selection"]
    rule = role["rule"]
    accent = role["accent"]
    foreground = role["foreground"]
    placeholder = role["placeholder"]
    hover = mix(sidebar, field, 0.5)
    quiet_selection = mix(selection, sidebar, 0.55)

    assigned = {
        "editor.background": editor,
        "editorGutter.background": editor,
        "editorPane.background": editor,
        "editorGroup.emptyBackground": editor,
        "breadcrumb.background": editor,
        "terminal.background": editor,
        "outputView.background": editor,
        "tab.activeBackground": editor,
        "tab.activeForeground": accent,

        "panel.background": panel,

        "sideBar.background": sidebar,
        "sideBar.border": rule,
        "tab.inactiveBackground": sidebar,
        "tab.unfocusedInactiveBackground": sidebar,
        "tab.unfocusedActiveBackground": sidebar,
        "tab.hoverForeground": accent,
        "dropdown.background": sidebar,
        "welcomePage.tileBackground": sidebar,
        "peekViewEditor.background": sidebar,
        "peekViewEditorGutter.background": sidebar,
        "peekViewResult.background": sidebar,
        "commandCenter.background": sidebar,

        "activityBar.background": frame,
        "activityBar.foreground": accent,
        "activityBar.border": rule,
        "titleBar.activeBackground": frame,
        "titleBar.inactiveBackground": frame,
        "titleBar.border": rule,
        "statusBar.background": frame,
        "statusBar.border": rule,
        "statusBar.noFolderBackground": frame,
        "statusBar.noFolderBorder": rule,
        "editorGroupHeader.tabsBackground": frame,
        "editorGroupHeader.noTabsBackground": frame,
        "editorGroupHeader.tabsBorder": frame,
        "editorGroupHeader.border": frame,
        "tab.border": frame,
        "sideBarSectionHeader.background": frame,
        "sideBarTitle.foreground": accent,
        "panelSectionHeader.background": frame,
        "peekViewTitle.background": frame,
        "notificationCenterHeader.background": frame,
        "quickInputTitle.background": frame,
        "debugToolBar.background": frame,
        "outputViewStickyScroll.background": frame,

        "input.background": field,
        "input.placeholderForeground": placeholder,
        "checkbox.background": field,
        "dropdown.listBackground": field,
        "editorWidget.background": field,
        "editorWidget.border": rule,
        "editorHoverWidget.background": field,
        "editorHoverWidget.border": rule,
        "editorSuggestWidget.background": field,
        "editorSuggestWidget.border": rule,
        "editorSuggestWidget.selectedBackground": selection,
        "editorMarkerNavigation.background": field,
        "quickInput.background": field,
        "menu.background": field,
        "menu.border": rule,
        "menu.selectionBackground": selection,
        "notifications.background": field,
        "breadcrumbPicker.background": field,
        "listFilterWidget.background": field,
        "settings.dropdownBackground": field,
        "settings.textInputBackground": field,
        "settings.numberInputBackground": field,
        "settings.checkboxBackground": field,
        "welcomePage.background": editor,

        "list.activeSelectionBackground": selection,
        "list.activeSelectionForeground": foreground,
        "list.focusBackground": selection,
        "list.focusForeground": foreground,
        "list.inactiveSelectionBackground": quiet_selection,
        "list.hoverBackground": hover,
        "quickInputList.focusBackground": selection,

        "editorGroup.border": rule,
        "panel.border": rule,
        "terminal.border": rule,
        "sideBarSectionHeader.border": rule,
    }
    return assigned


def active_theme_name(home: Path) -> str:
    path = home / ".local/state/omarchy/current/theme.name"
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def refresh_editors() -> None:
    # The theme file is copied into each editor when this runs. A second call
    # after the patch bumps the local extension version so VS Code reloads it.
    if os.environ.get("OMARCHY_THEME_HEADLESS") == "1":
        return
    subprocess.run(["omarchy-theme-set-vscode"], check=False)


def apply(
    home: Path,
    colors_path: Path | None = None,
    theme_path: Path | None = None,
    force: bool = False,
    refresh: bool = True,
) -> int:
    theme = active_theme_name(home)
    if not force and theme != THEME_NAME:
        return 0

    state = home / ".local/state/omarchy/current/theme"
    if colors_path is None:
        colors_path = state / "colors.toml"
    if theme_path is None:
        theme_path = state / THEME_FILE
    if not theme_path.is_file():
        return 0

    try:
        colors = load_colors(colors_path)
        updates = chrome(colors)
        data = json.loads(theme_path.read_text())
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return 0
    if not updates or not isinstance(data, dict):
        return 0

    workbench = data.get("colors")
    if not isinstance(workbench, dict):
        return 0

    changed = False
    for key, value in updates.items():
        if workbench.get(key) != value:
            workbench[key] = value
            changed = True
    if not changed:
        return 0

    data["colors"] = workbench
    text = json.dumps(data, indent=4) + "\n"
    tmp = theme_path.with_name(theme_path.name + ".lcars-tmp")
    tmp.write_text(text)
    tmp.replace(theme_path)
    if refresh:
        refresh_editors()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="apply even when the active theme is not LCARS")
    parser.add_argument("--colors", type=Path, help="colors.toml to read (implies --force)")
    parser.add_argument("--theme", type=Path, help="vscode-theme.json to patch")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--no-refresh", action="store_true", help="do not reload VS Code, Cursor, or Codium")
    args = parser.parse_args()
    force = args.force or args.colors is not None
    return apply(
        args.home,
        colors_path=args.colors,
        theme_path=args.theme,
        force=force,
        refresh=not args.no_refresh,
    )


if __name__ == "__main__":
    raise SystemExit(main())
