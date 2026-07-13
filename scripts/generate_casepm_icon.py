"""Generate Case PM icons matching the login page (emerald tile + hard hat)."""
from __future__ import annotations

import io
import os
import sys

import fitz
from PIL import Image

# Font Awesome 6 solid hard-hat / helmet-safety (same glyph as login page)
HARD_HAT_PATH = (
    'M256 32c-17.7 0-32 14.3-32 32v2.3 99.6c0 5.6-4.5 10.1-10.1 10.1c-3.6 0-7-1.9-8.8-5.1L157.1 87C83 123.5 32 199.8 32 288v64H544l0-66.4'
    '-.9-87.2-51.7-162.4-125.1-198.6l-48 83.9c-1.8 3.2-5.2 5.1-8.8 5.1c-5.6 0-10.1-4.5-10.1-10.1V66.3 64c0-17.7-14.3-32-32-32H256z'
    'M16.6 384C7.4 384 0 391.4 0 400.6c0 4.7 2 9.2 5.8 11.9C27.5 428.4 111.8 480 288 480s260.5-51.6 282.2-67.5c3.8-2.8 5.8-7.2 5.8-11.9c0-9.2-7.4-16.6-16.6-16.6H16.6z'
)

EMERALD = '#059669'


def _svg_for(size: int) -> str:
    pad = round(size * 0.06)
    inner = size - pad * 2
    radius = round(size * 0.18)
    icon_w = round(inner * 0.62)
    icon_h = round(icon_w * 512 / 576)
    icon_x = pad + (inner - icon_w) // 2
    icon_y = pad + (inner - icon_h) // 2 - round(size * 0.01)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <rect x="{pad}" y="{pad}" width="{inner}" height="{inner}" rx="{radius}" fill="{EMERALD}"/>
  <svg x="{icon_x}" y="{icon_y}" width="{icon_w}" height="{icon_h}" viewBox="0 0 576 512">
    <path fill="#ffffff" d="{HARD_HAT_PATH}"/>
  </svg>
</svg>'''


def render_png(size: int) -> Image.Image:
    svg = _svg_for(size)
    doc = fitz.open(stream=svg.encode(), filetype='svg')
    pix = doc[0].get_pixmap(alpha=True)
    return Image.open(io.BytesIO(pix.tobytes('png')))


def write_icons(root: str | None = None) -> None:
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_img = os.path.join(root, 'static', 'img')
    connector_dir = os.path.join(root, 'connector')
    os.makedirs(static_img, exist_ok=True)
    os.makedirs(connector_dir, exist_ok=True)

    sizes = [16, 32, 48, 64, 128, 256]
    icons = [render_png(s) for s in sizes]
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
    print('Wrote Case PM icons to static/img and connector/')


if __name__ == '__main__':
    write_icons(sys.argv[1] if len(sys.argv) > 1 else None)
