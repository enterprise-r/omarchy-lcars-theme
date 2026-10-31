#!/usr/bin/env python3
"""Draw assets/palette.png from colors.toml.

Needs Pillow, Nimbus Sans Narrow Bold, and JetBrains Mono.
"""

import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "palette.png"

W, H = 2560, 1600
SCALE = 3
PAGE = "#000000"

NARROW = "/usr/share/fonts/gsfonts/NimbusSansNarrow-Bold.otf"
MONO = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"

SURFACES = [
    ("darker_background", "DARKER BACKGROUND"),
    ("dark_background", "DARK BACKGROUND"),
    ("background", "BACKGROUND"),
    ("lighter_background", "LIGHTER BACKGROUND"),
    ("selection", "SELECTION"),
    ("muted", "MUTED"),
    ("hyprland_inactive_border", "INACTIVE BORDER"),
]
NAMED = [
    ("red", "RED", "bright_red", "BRIGHT RED"),
    ("yellow", "YELLOW", "bright_yellow", "BRIGHT YELLOW"),
    ("orange", "ORANGE", "accent", "ACCENT"),
    ("green", "GREEN", "bright_green", "BRIGHT GREEN"),
    ("cyan", "CYAN", "bright_cyan", "BRIGHT CYAN"),
    ("blue", "BLUE", "bright_blue", "BRIGHT BLUE"),
    ("magenta", "MAGENTA", "bright_magenta", "BRIGHT MAGENTA"),
    ("brown", "BROWN", "hyprland_active_border", "ACTIVE BORDER"),
]
INKS = [
    ("dark_foreground", "DARK FOREGROUND"),
    ("foreground", "FOREGROUND"),
    ("light_foreground", "LIGHT FOREGROUND"),
    ("bright_foreground", "BRIGHT FOREGROUND"),
]


def rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def luminance(value):
    def channel(part):
        part = part / 255
        if part <= 0.04045:
            return part / 12.92
        return ((part + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(part) for part in rgb(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(foreground, background):
    lighter = max(luminance(foreground), luminance(background))
    darker = min(luminance(foreground), luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def best_ink(fill, dark, light):
    dark_contrast = contrast(dark, fill)
    light_contrast = contrast(light, fill)
    if dark_contrast >= light_contrast and dark_contrast >= 4.5:
        return dark
    if light_contrast > dark_contrast and light_contrast >= 4.5:
        return light
    return dark if dark_contrast >= light_contrast else light


def hex_label(value):
    return value.upper()


class Board:
    def __init__(self, colors):
        self.colors = colors
        self.dark = colors["background"]
        self.light = colors["bright_foreground"]
        self.image = Image.new("RGB", (W * SCALE, H * SCALE), PAGE)
        self.draw = ImageDraw.Draw(self.image)
        self.narrow = {}
        self.mono = {}

    def font(self, kind, size):
        cache = self.narrow if kind == "narrow" else self.mono
        path = NARROW if kind == "narrow" else MONO
        if size not in cache:
            cache[size] = ImageFont.truetype(path, size * SCALE)
        return cache[size]

    def tracked_width(self, text, font, tracking):
        if not text:
            return 0
        return sum(font.getlength(ch) for ch in text) + tracking * SCALE * (len(text) - 1)

    def text(self, xy, text, font, fill, tracking=0, anchor="lm"):
        x, y = xy
        x *= SCALE
        y *= SCALE
        if tracking:
            widths = [font.getlength(ch) for ch in text]
            total = sum(widths) + tracking * SCALE * (len(text) - 1)
            if anchor[0] == "m":
                x -= total / 2
            elif anchor[0] == "r":
                x -= total
            for ch, width in zip(text, widths):
                self.draw.text((x, y), ch, font=font, fill=fill, anchor="l" + anchor[1])
                x += width + tracking * SCALE
            return
        self.draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

    def rounded(self, box, radius, fill, outline=None, width=0):
        x, y, w, h = box
        xy = [x * SCALE, y * SCALE, (x + w) * SCALE, (y + h) * SCALE]
        kwargs = {"radius": radius * SCALE, "fill": fill}
        if outline and width:
            kwargs["outline"] = outline
            kwargs["width"] = max(1, round(width * SCALE))
        self.draw.rounded_rectangle(xy, **kwargs)

    def ink(self, fill):
        return best_ink(fill, self.dark, self.light)

    def pill(self, box, fill, label, code):
        x, y, w, h = box
        # Near-black fills disappear on the page. Ring them with muted
        # without letting the ring replace the sampled color.
        if contrast(fill, PAGE) < 1.8:
            ring = self.colors["muted"]
            self.rounded((x, y, w, h), h / 2, ring)
            inset = 4
            self.rounded(
                (x + inset, y + inset, w - inset * 2, h - inset * 2),
                max(0, h / 2 - inset),
                fill,
            )
        else:
            self.rounded((x, y, w, h), h / 2, fill)

        ink = self.ink(fill)
        label_font = self.font("narrow", 36)
        code_font = self.font("mono", 30)
        label_track = 2
        pad = 36
        label_w = self.tracked_width(label, label_font, label_track) / SCALE
        code_w = self.tracked_width(code, code_font, 0) / SCALE
        if label_w + code_w + pad * 2 + 24 > w:
            label_track = 0
        self.text((x + pad, y + h / 2), label, label_font, ink, label_track, "lm")
        self.text((x + w - pad, y + h / 2), code, code_font, ink, 0, "rm")

    def header_pill(self, box, fill, label, size, tracking):
        x, y, w, h = box
        self.rounded((x, y, w, h), h / 2, fill)
        self.text(
            (x + w / 2, y + h / 2),
            label,
            self.font("narrow", size),
            self.ink(fill),
            tracking,
            "mm",
        )

    def save(self, path):
        out = self.image.resize((W, H), Image.Resampling.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(path, "PNG", optimize=True)


def load_colors():
    data = tomllib.loads((ROOT / "colors.toml").read_text())
    mode = data.pop("mode")
    if mode != "dark":
        raise SystemExit(f"unexpected mode {mode}")
    return data


def render(colors):
    for path in (NARROW, MONO):
        if not Path(path).is_file():
            raise SystemExit(f"missing font {path}")

    board = Board(colors)
    margin = 64
    header = (64, 52, W - 128, 112)

    def pill_width(label, size, tracking, min_w):
        font = board.font("narrow", size)
        return max(min_w, round(board.tracked_width(label, font, tracking) / SCALE + 160))

    accent_code = hex_label(colors["accent"])
    left_w = pill_width("LCARS", 54, 10, 340)
    center_w = pill_width("COLOR INDEX", 48, 6, 620)
    right_w = pill_width(accent_code, 44, 2, 420)
    hx, hy, hw, hh = header
    left_box = (hx, hy, left_w, hh)
    right_box = (hx + hw - right_w, hy, right_w, hh)
    center_box = (hx + (hw - center_w) / 2, hy, center_w, hh)

    board.header_pill(left_box, colors["accent"], "LCARS", 54, 10)
    board.header_pill(center_box, colors["magenta"], "COLOR INDEX", 48, 6)
    board.header_pill(right_box, colors["accent"], accent_code, 44, 2)

    section_font = board.font("narrow", 30)
    section_y = 196
    col_gap = 36
    col_w = (W - margin * 2 - col_gap) // 2
    left_x = margin
    right_x = margin + col_w + col_gap
    board.text((left_x, section_y), "SURFACES", section_font, colors["accent"], 4, "lt")
    board.text((right_x, section_y), "NAMED COLORS", section_font, colors["accent"], 4, "lt")

    pills_y = 248
    row_h = 98
    row_gap = 14
    stack = len(NAMED) * row_h + (len(NAMED) - 1) * row_gap
    left_gap = 14
    left_h = (stack - (len(SURFACES) - 1) * left_gap) / len(SURFACES)

    for index, (key, label) in enumerate(SURFACES):
        y = pills_y + index * (left_h + left_gap)
        board.pill((left_x, y, col_w, left_h), colors[key], label, hex_label(colors[key]))

    pair_gap = 16
    pair_w = (col_w - pair_gap) / 2
    for index, (left_key, left_label, right_key, right_label) in enumerate(NAMED):
        y = pills_y + index * (row_h + row_gap)
        board.pill((right_x, y, pair_w, row_h), colors[left_key], left_label, hex_label(colors[left_key]))
        board.pill(
            (right_x + pair_w + pair_gap, y, pair_w, row_h),
            colors[right_key],
            right_label,
            hex_label(colors[right_key]),
        )

    panel_y = pills_y + stack + 40
    panel_h = H - 56 - panel_y
    panels = [
        (left_x, "background", "BACKGROUND"),
        (right_x, "lighter_background", "LIGHTER BACKGROUND"),
    ]
    name_font = board.font("narrow", 30)
    sample_font = board.font("narrow", 40)
    code_font = board.font("mono", 28)
    title_font = board.font("narrow", 30)
    sample = "A quiet view at warp."

    for x, surface_key, surface_label in panels:
        fill = colors[surface_key]
        board.rounded((x, panel_y, col_w, panel_h), 28, fill, colors["hyprland_active_border"], 4)
        pad = 36
        title_y = panel_y + 34
        board.text((x + pad, title_y), "LCARS", title_font, colors["accent"], 3, "lt")
        brand_w = board.tracked_width("LCARS", title_font, 3) / SCALE
        board.text((x + pad + brand_w + 16, title_y), "/", title_font, colors["muted"], 0, "lt")
        board.text(
            (x + pad + brand_w + 40, title_y),
            surface_label,
            title_font,
            colors["light_foreground"],
            2,
            "lt",
        )
        board.text((x + col_w - pad, title_y + 4), hex_label(fill), code_font, colors["muted"], 0, "rt")

        top = panel_y + 92
        bottom = panel_y + panel_h - 28
        slot = (bottom - top) / len(INKS)
        for index, (key, label) in enumerate(INKS):
            ink = colors[key]
            cy = top + slot * index + slot / 2
            if index:
                line_y = top + slot * index
                board.draw.line(
                    [(x + pad) * SCALE, line_y * SCALE, (x + col_w - pad) * SCALE, line_y * SCALE],
                    fill=colors["selection"],
                    width=SCALE,
                )
            board.text((x + pad, cy), label, name_font, ink, 1, "lm")
            name_w = board.tracked_width(label, name_font, 1) / SCALE
            board.text((x + pad + max(name_w + 36, 430), cy), sample, sample_font, ink, 0, "lm")
            board.text((x + col_w - pad, cy), hex_label(ink), code_font, ink, 0, "rm")

    shown = {key for key, _label in SURFACES}
    shown.update(key for key, _label in INKS)
    for left_key, _left_label, right_key, _right_label in NAMED:
        shown.add(left_key)
        shown.add(right_key)
    missing = sorted(set(colors) - shown)
    if missing:
        raise SystemExit(f"missing from board: {missing}")

    board.save(OUT)


def main():
    render(load_colors())
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
