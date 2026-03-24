#!/usr/bin/env python3
"""Generate branding assets for the integration and companion add-on.

Renders the Finance Dashboard coin icon (gold rim, green face, smiley)
as 256x256 PNGs in both light and dark mode variants.

Output locations:
  - finance_dashboard_companion/  (icon.png, logo.png, dark_icon.png, dark_logo.png)
  - custom_components/finance_dashboard/brand/  (same 4 files)
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ADDON_DIR = REPO_ROOT / "finance_dashboard_companion"
BRAND_DIR = REPO_ROOT / "custom_components" / "finance_dashboard" / "brand"


def chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack("!I", len(data))
        + tag
        + data
        + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        row = pixels[y * width : (y + 1) * width]
        for r, g, b, a in row:
            raw.extend((r, g, b, a))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def clamp(value: float) -> int:
    return max(0, min(255, int(round(value))))


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(clamp(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render_icon(size: int, dark: bool) -> list[tuple[int, int, int, int]]:
    """Render the Finance Dashboard coin icon.

    Design: dual-tone coin with a friendly face.
    - Outer gold ring (coin edge)
    - Inner green circle (face)
    - Two dark eyes with green highlights
    - Curved smile
    """
    pixels: list[tuple[int, int, int, int]] = []

    # Color palette
    if not dark:
        coin_outer = (244, 185, 66)      # #f4b942 — gold
        coin_stroke = (229, 166, 48)      # #e5a630 — darker gold
        face_fill = (78, 204, 163)        # #4ecca3 — green
        face_stroke = (58, 184, 143)      # #3ab88f — darker green
        eye_color = (26, 26, 46)          # #1a1a2e — dark
        bg_alpha = 0                      # transparent background
    else:
        coin_outer = (204, 155, 46)       # dimmed gold for dark mode
        coin_stroke = (184, 136, 28)      # dimmed stroke
        face_fill = (58, 174, 133)        # dimmed green
        face_stroke = (48, 154, 113)      # dimmed green stroke
        eye_color = (220, 220, 240)       # light eyes for dark bg
        bg_alpha = 0                      # transparent background

    eye_highlight = face_fill
    smile_color = eye_color

    center = size / 2
    coin_radius = size * 0.461            # ~236/512
    coin_stroke_width = size * 0.0156     # ~8/512
    face_radius = size * 0.336            # ~172/512
    face_stroke_width = size * 0.00586    # ~3/512

    # Eye positions (relative to center, scaled from 512 to size)
    eye_left_x = center + (200 - 256) * size / 512
    eye_left_y = center + (216 - 256) * size / 512
    eye_right_x = center + (312 - 256) * size / 512
    eye_right_y = center + (216 - 256) * size / 512
    eye_radius = 20 * size / 512

    # Eye highlight offset
    hl_left_x = center + (195 - 256) * size / 512
    hl_left_y = center + (211 - 256) * size / 512
    hl_right_x = center + (307 - 256) * size / 512
    hl_right_y = center + (211 - 256) * size / 512
    hl_radius = 7 * size / 512

    # Smile arc (approximate the quadratic bezier from SVG)
    smile_y_center = (292) * size / 512
    smile_x_left = (184) * size / 512
    smile_x_right = (328) * size / 512
    smile_width = 18 * size / 512

    for y in range(size):
        for x in range(size):
            px = x + 0.5
            py = y + 0.5

            dx = px - center
            dy = py - center
            distance = math.hypot(dx, dy)

            color = (0, 0, 0)
            alpha = bg_alpha

            # Coin outer fill
            if distance <= coin_radius:
                color = coin_outer
                alpha = 255

            # Coin stroke (outer ring edge)
            if abs(distance - coin_radius) < coin_stroke_width:
                color = coin_stroke
                alpha = 255

            # Face fill
            if distance <= face_radius:
                color = face_fill
                alpha = 255

            # Face stroke
            if abs(distance - face_radius) < face_stroke_width:
                color = face_stroke
                alpha = 255

            # Left eye
            eye_dist = math.hypot(px - eye_left_x, py - eye_left_y)
            if eye_dist <= eye_radius:
                color = eye_color
                alpha = 255

            # Left eye highlight
            hl_dist = math.hypot(px - hl_left_x, py - hl_left_y)
            if hl_dist <= hl_radius:
                color = eye_highlight
                alpha = 255

            # Right eye
            eye_dist = math.hypot(px - eye_right_x, py - eye_right_y)
            if eye_dist <= eye_radius:
                color = eye_color
                alpha = 255

            # Right eye highlight
            hl_dist = math.hypot(px - hl_right_x, py - hl_right_y)
            if hl_dist <= hl_radius:
                color = eye_highlight
                alpha = 255

            # Smile arc (quadratic bezier: M 184 292 Q 256 372 328 292)
            # Parametric: for each x, compute y on the curve
            if smile_x_left <= px <= smile_x_right:
                t = (px - smile_x_left) / (smile_x_right - smile_x_left)
                # Quadratic bezier: P = (1-t)^2*P0 + 2*(1-t)*t*P1 + t^2*P2
                p0_y = 292 * size / 512
                p1_y = 372 * size / 512
                p2_y = 292 * size / 512
                curve_y = (1 - t) ** 2 * p0_y + 2 * (1 - t) * t * p1_y + t ** 2 * p2_y
                dist_to_curve = abs(py - curve_y)
                if dist_to_curve < smile_width / 2 and py >= p0_y - smile_width / 2:
                    color = smile_color
                    alpha = 255

            pixels.append((color[0], color[1], color[2], alpha))

    return pixels


def main() -> int:
    print("Generating Finance Dashboard branding assets...")

    addon_icon = render_icon(256, dark=False)
    addon_dark = render_icon(256, dark=True)

    # Companion add-on directory
    write_png(ADDON_DIR / "icon.png", 256, 256, addon_icon)
    write_png(ADDON_DIR / "logo.png", 256, 256, addon_icon)
    write_png(ADDON_DIR / "dark_icon.png", 256, 256, addon_dark)
    write_png(ADDON_DIR / "dark_logo.png", 256, 256, addon_dark)
    print(f"  Written: {ADDON_DIR}/{{icon,logo,dark_icon,dark_logo}}.png")

    # Integration brand directory
    integration_icon = render_icon(256, dark=False)
    integration_dark = render_icon(256, dark=True)
    write_png(BRAND_DIR / "icon.png", 256, 256, integration_icon)
    write_png(BRAND_DIR / "logo.png", 256, 256, integration_icon)
    write_png(BRAND_DIR / "dark_icon.png", 256, 256, integration_dark)
    write_png(BRAND_DIR / "dark_logo.png", 256, 256, integration_dark)
    print(f"  Written: {BRAND_DIR}/{{icon,logo,dark_icon,dark_logo}}.png")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
