#!/usr/bin/env python3
"""Paint VS Code chrome with the Dark-R roles.

Omarchy's generated theme paints every region with one background and uses
translucent accent washes for hover and selection. This patches the workbench
colors in vscode-theme.json from the same roles as the GTK and Firefox hooks:
the code well stays `background`, sidebars, panels and fields are cards, the
title bar is the app header strip, the current tab is sage, keyboard rows in
the launcher, suggestions and menus are solid amber, and warnings are amber.

VS Code has no hover color for match highlights or toolbar icons, so lists
and toolbars hover with the quiet `--ui-border` fill instead of amber; an
amber fill would hide the amber matches and the light icons. The keyboard
cursor in those lists is a solid amber outline.
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


def chrome(colors: dict[str, str]) -> dict[str, str]:
    """Workbench colors for a dark theme; empty for a light one."""
    r = roles(colors)
    bg, fg, card, line, edge = r["bg"], r["fg"], r["card"], r["line"], r["edge"]
    if luminance(bg) > luminance(fg):
        return {}
    dim, bright, hover, primary = r["dim"], r["bright"], r["hover"], r["primary"]
    on_hover = on_color(hover, bg, fg)
    on_primary = on_color(primary, bg, fg)
    on_primary_hover = on_color(r["primary_hover"], bg, fg)
    on_warn = on_color(r["warn"], bg, fg)
    warn = r["warn"]

    return {
        # Code well.
        "editor.background": bg,
        "editorGutter.background": bg,
        "editorPane.background": bg,
        "editorGroup.emptyBackground": bg,
        "breadcrumb.background": bg,
        "terminal.background": bg,
        "outputView.background": bg,
        "welcomePage.background": bg,
        "editor.lineHighlightBackground": card,
        "editor.lineHighlightBorder": line,

        # App header strip, as the GTK header bar and Firefox toolbar.
        "titleBar.activeBackground": r["bar"],
        "titleBar.activeForeground": fg,
        "titleBar.inactiveBackground": card,
        "titleBar.inactiveForeground": fg,
        "titleBar.border": edge,

        # Cards: sidebars, panels, frame. Quiet rules keep regions apart.
        "panel.background": card,
        "panel.border": line,
        "sideBar.background": card,
        "sideBar.border": line,
        "sideBarTitle.foreground": fg,
        "sideBarSectionHeader.background": card,
        "sideBarSectionHeader.border": line,
        "panelSectionHeader.background": card,
        "activityBar.background": card,
        "activityBar.border": line,
        "statusBar.background": card,
        "statusBar.border": line,
        "statusBar.noFolderBackground": card,
        "statusBar.noFolderBorder": line,
        "editorGroupHeader.tabsBackground": card,
        "editorGroupHeader.noTabsBackground": card,
        "editorGroupHeader.tabsBorder": line,
        "editorGroupHeader.border": line,
        "editorGroup.border": line,
        "terminal.border": line,
        "welcomePage.tileBackground": card,
        "peekViewEditor.background": card,
        "peekViewEditorGutter.background": card,
        "peekViewResult.background": card,
        "peekViewTitle.background": card,
        "commandCenter.background": card,
        "notificationCenterHeader.background": card,
        "quickInputTitle.background": card,
        "debugToolBar.background": card,
        "outputViewStickyScroll.background": card,

        # Popups are cards with a dim edge.
        "widget.border": edge,
        "editorWidget.background": card,
        "editorWidget.border": edge,
        "editorHoverWidget.background": card,
        "editorHoverWidget.border": edge,
        "editorSuggestWidget.background": card,
        "editorSuggestWidget.border": edge,
        "editorMarkerNavigation.background": card,
        "quickInput.background": card,
        "menu.background": card,
        "menu.border": edge,
        "notifications.background": card,
        "notifications.border": edge,
        "notificationToast.border": edge,
        "breadcrumbPicker.background": card,
        "listFilterWidget.background": card,

        # Fields: card fill, dim border, dim placeholder.
        "input.background": card,
        "input.border": edge,
        "input.placeholderForeground": dim,
        "dropdown.background": card,
        "dropdown.listBackground": card,
        "dropdown.border": edge,
        "checkbox.background": card,
        "checkbox.border": edge,
        "checkbox.selectBackground": card,
        "checkbox.selectBorder": edge,
        "settings.dropdownBackground": card,
        "settings.textInputBackground": card,
        "settings.numberInputBackground": card,
        "settings.checkboxBackground": card,
        "descriptionForeground": dim,
        "editorLineNumber.foreground": dim,

        # Tabs: sage marks the current one, amber is hover.
        "tab.activeBackground": bg,
        "tab.activeForeground": primary,
        "tab.activeBorder": primary,
        "tab.activeBorderTop": primary,
        "tab.unfocusedActiveBackground": card,
        "tab.unfocusedActiveBorderTop": primary,
        "tab.inactiveBackground": card,
        "tab.unfocusedInactiveBackground": card,
        "tab.inactiveForeground": dim,
        "tab.unfocusedInactiveForeground": dim,
        "tab.border": line,
        "tab.hoverBackground": hover,
        "tab.hoverForeground": on_hover,
        "tab.unfocusedHoverBackground": hover,
        "tab.unfocusedHoverForeground": on_hover,
        "tab.hoverBorder": hover,

        # Activity bar: sage for the current view, no wash behind it.
        "activityBar.foreground": primary,
        "activityBar.inactiveForeground": fg,
        "activityBar.activeBorder": primary,
        "activityBar.activeBackground": card,

        # Launcher, suggestions and menus: the keyboard row is solid amber.
        "quickInputList.focusBackground": hover,
        "quickInputList.focusForeground": on_hover,
        "quickInputList.focusIconForeground": on_hover,
        "list.focusHighlightForeground": on_hover,
        "editorSuggestWidget.selectedBackground": hover,
        "editorSuggestWidget.selectedForeground": on_hover,
        "editorSuggestWidget.selectedIconForeground": on_hover,
        "editorSuggestWidget.focusHighlightForeground": on_hover,
        "menu.selectionBackground": hover,
        "menu.selectionForeground": on_hover,
        "menu.selectionBorder": hover,
        "menubar.selectionBackground": hover,
        "menubar.selectionForeground": on_hover,
        "statusBarItem.hoverBackground": hover,
        "statusBarItem.hoverForeground": on_hover,
        "statusBarItem.prominentHoverBackground": hover,
        "statusBarItem.prominentHoverForeground": on_hover,
        "statusBarItem.remoteHoverBackground": hover,
        "statusBarItem.remoteHoverForeground": on_hover,

        # Trees and lists keep amber matches readable: quiet fills, the
        # keyboard cursor as an amber outline, the chosen row in sage.
        "list.hoverBackground": line,
        "list.hoverForeground": fg,
        "list.focusBackground": line,
        "list.focusForeground": fg,
        "list.focusOutline": hover,
        "list.focusAndSelectionOutline": hover,
        "list.activeSelectionBackground": line,
        "list.activeSelectionForeground": primary,
        "list.activeSelectionIconForeground": primary,
        "list.inactiveSelectionBackground": line,
        "list.inactiveSelectionForeground": fg,
        "list.inactiveFocusBackground": line,
        "list.inactiveFocusOutline": edge,
        "list.highlightForeground": hover,
        "toolbar.hoverBackground": line,
        "toolbar.activeBackground": line,
        "inputOption.hoverBackground": line,
        "settings.focusedRowBackground": line,
        "settings.focusedRowBorder": hover,
        "settings.rowHoverBackground": line,
        "peekViewResult.selectionBackground": line,

        # Buttons and toggles: sage when suggested or on, amber on hover.
        "button.background": primary,
        "button.foreground": on_primary,
        "button.hoverBackground": r["primary_hover"],
        "button.border": edge,
        "button.secondaryBackground": line,
        "button.secondaryForeground": fg,
        "button.secondaryHoverBackground": card,
        "inputOption.activeBackground": primary,
        "inputOption.activeForeground": on_primary,
        "inputOption.activeBorder": primary,
        "progressBar.background": primary,

        # Focus and links.
        "focusBorder": r["focus"],
        "textLink.foreground": r["link"],
        "textLink.activeForeground": r["link_hover"],

        # Notices: warnings are amber; info, error stay blue and red.
        "editorWarning.foreground": warn,
        "editorWarning.background": f"{warn}15",
        "editorOverviewRuler.warningForeground": warn,
        "minimap.warningHighlight": warn,
        "problemsWarningIcon.foreground": warn,
        "notificationsWarningIcon.foreground": warn,
        "list.warningForeground": warn,
        "inputValidation.warningForeground": warn,
        "inputValidation.warningBorder": warn,
        "inputValidation.warningBackground": f"{warn}20",
        "editorMarkerNavigationWarning.background": f"{warn}20",
        "editorMarkerNavigationWarning.headerBackground": f"{warn}15",
        "debugConsole.warningForeground": warn,
        "statusBarItem.warningBackground": warn,
        "statusBarItem.warningForeground": on_warn,
        "statusBarItem.warningHoverBackground": warn,
        "statusBarItem.warningHoverForeground": on_warn,
        "editorInfo.foreground": r["info"],
        "notificationsInfoIcon.foreground": r["info"],
        "editorError.foreground": r["error"],
        "notificationsErrorIcon.foreground": r["error"],
    }


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
