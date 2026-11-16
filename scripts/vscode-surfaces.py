#!/usr/bin/env python3
"""Separate VS Code chrome with the named LCARS surfaces.

Omarchy's generated theme paints the activity bar, sidebar, editor, panel,
and title bar with one background. The code well stays `background`. Cards,
sidebars, panels, inputs, and the activity/title/status frame share
`lighter_background`, split by the inactive border. The current tab and
activity icon use green. Amber is hover only.
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


def luma(color: str) -> float:
    r, g, b = _rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def load_colors(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text())
    required = ("background", "foreground", "accent")
    for key in required:
        if not hex_ok(data.get(key)):
            raise ValueError(f"bad or missing color {key!r} in {path}")
    optional = (
        "lighter_background",
        "selection",
        "green",
        "magenta",
        "bright_magenta",
        "bright_foreground",
        "blue",
        "muted",
        "light_foreground",
        "dark_foreground",
        "hyprland_inactive_border",
        "hyprland_active_border",
    )
    out = {key: data[key] for key in required}
    for key in optional:
        if hex_ok(data.get(key)):
            out[key] = data[key]
    return out


def surfaces(colors: dict[str, str]) -> dict[str, str] | None:
    """Named roles. Chrome shares the card; borders keep the regions apart.

    The editor stays on `background`. Sidebar, panel, frame, and fields use
    `lighter_background`. Idle rules use the inactive border. Widget edges
    that have to read clearly use `dark_foreground`.
    """
    editor = colors["background"]
    foreground = colors["foreground"]
    if luma(editor) > luma(foreground):
        return None

    card = colors.get("lighter_background", editor)
    idle = colors.get("hyprland_inactive_border", colors.get("selection", card))
    visible = colors.get("dark_foreground", colors.get("muted", foreground))
    active = colors.get("magenta") or colors.get("hyprland_active_border") or colors["accent"]
    selection = colors.get("selection", idle)
    return {
        "editor": editor,
        "panel": card,
        "sidebar": card,
        "frame": card,
        "field": card,
        "selection": selection,
        "hover": idle,
        "rule": idle,
        "edge": visible,
        "active_edge": active,
        "focus": colors.get("bright_foreground", foreground),
        "accent": colors["accent"],
        "current": colors.get("green", colors["accent"]),
        "link": colors.get("bright_magenta", active),
        "foreground": foreground,
        "placeholder": colors.get("dark_foreground", colors.get("muted", foreground)),
        "inactive_icon": colors.get("light_foreground", foreground),
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
    edge = role["edge"]
    active_edge = role["active_edge"]
    accent = role["accent"]
    current = role["current"]
    focus = role["focus"]
    link = role["link"]
    foreground = role["foreground"]
    placeholder = role["placeholder"]
    inactive_icon = role["inactive_icon"]
    hover = role["hover"]

    assigned = {
        "editor.background": editor,
        "editorGutter.background": editor,
        "editorPane.background": editor,
        "editorGroup.emptyBackground": editor,
        "breadcrumb.background": editor,
        "terminal.background": editor,
        "outputView.background": editor,
        "tab.activeBackground": editor,
        "tab.activeForeground": current,
        "tab.activeBorder": current,
        "tab.activeBorderTop": current,

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
        "activityBar.foreground": current,
        "activityBar.inactiveForeground": inactive_icon,
        "activityBar.activeBorder": current,
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
        "editorGroupHeader.tabsBorder": rule,
        "editorGroupHeader.border": rule,
        "tab.border": rule,
        "sideBarSectionHeader.background": frame,
        "sideBarTitle.foreground": inactive_icon,
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
        "editorWidget.border": edge,
        "editorHoverWidget.background": field,
        "editorHoverWidget.border": edge,
        "editorSuggestWidget.background": field,
        "editorSuggestWidget.border": edge,
        "editorSuggestWidget.selectedBackground": selection,
        "editorMarkerNavigation.background": field,
        "quickInput.background": field,
        "menu.background": field,
        "menu.border": edge,
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
        "list.inactiveSelectionBackground": hover,
        "list.hoverBackground": hover,
        "quickInputList.focusBackground": selection,

        "focusBorder": focus,
        "textLink.foreground": link,
        "textLink.activeForeground": focus,

        "editorGroup.border": active_edge,
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
