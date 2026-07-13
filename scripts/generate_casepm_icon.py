"""Generate Case PM icons matching the login header (w-9 emerald tile + fa-hard-hat)."""
from __future__ import annotations

import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

# Login header: w-9 h-9 (36px), bg-emerald-600, rounded-lg (8px), fa-hard-hat text-base (16px)
TILE_PX = 36
RADIUS_PX = 8
GLYPH_PX = 16
EMERALD = '#059669'
WHITE = '#ffffff'
HARD_HAT = '\uf807'  # Font Awesome 6 solid hard-hat


def _font_path(root: str) -> str:
    path = os.path.join(root, 'static', 'fonts', 'fa-solid-900.ttf')
    if os.path.isfile(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = 'https://github.com/FortAwesome/Font-Awesome/raw/6.5.2/webfonts/fa-solid-900.ttf'
    print(f'Downloading Font Awesome font to {path} ...')
    urllib.request.urlretrieve(url, path)
    return path


def render_tile(size: int, font_path: str) -> Image.Image:
    """Render the login-header icon scaled to size x size pixels."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    scale = size / TILE_PX
    radius = max(1, round(RADIUS_PX * scale))
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=EMERALD)

    font_size = max(8, round(GLYPH_PX * scale))
    font = ImageFont.truetype(font_path, font_size)
    bbox = draw.textbbox((0, 0), HARD_HAT, font=font)
    gw = bbox[2] - bbox[0]
    gh = bbox[3] - bbox[1]
    x = (size - gw) // 2 - bbox[0]
    y = (size - gh) // 2 - bbox[1]
    draw.text((x, y), HARD_HAT, font=font, fill=WHITE)
    return img


def write_icons(root: str | None = None) -> None:
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    font_path = _font_path(root)
    static_img = os.path.join(root, 'static', 'img')
    connector_dir = os.path.join(root, 'connector')
    os.makedirs(static_img, exist_ok=True)
    os.makedirs(connector_dir, exist_ok=True)

    sizes = [16, 32, 48, 64, 128, 256]
    icons = [render_tile(s, font_path) for s in sizes]
    icons[-1].save(os.path.join(static_img, 'casepm-icon.png'), 'PNG')
    icons[4].save(os.path.join(static_img, 'casepm-icon-64.png'), 'PNG')
    ico_sizes = [(s, s) for s in sizes]
    icons[-1].save(
        os.path.join(static_img, 'casepm-icon.ico'),
        format='ICO',
        sizes=ico_sizes,
        append_images=icons[:-1],
    )
    icons[-1].save(
        os.path.join(connector_dir, 'casepm-icon.ico'),
        format='ICO',
        sizes=ico_sizes,
        append_images=icons[:-1],
    )
    print('Wrote Case PM icons (login-header match) to static/img and connector/')


if __name__ == '__main__':
    write_icons(sys.argv[1] if len(sys.argv) > 1 else None)
