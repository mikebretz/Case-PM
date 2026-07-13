"""Generate Case PM icons — browser-quality match to the login header tile."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

# Login header: w-9 h-9 (36px), rounded-lg (8px), fa-hard-hat text-base (16px)
HEADER_TILE_PX = 36
HEADER_RADIUS_PX = 8
HEADER_GLYPH_PX = 16
MASTER_PX = 1024
EMERALD_RGB = (5, 150, 105)  # #059669
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _template_path(root: Path) -> Path:
    return root / 'scripts' / 'casepm-icon-template.html'


def _flatten_emerald(img: Image.Image) -> Image.Image:
    """Opaque emerald background — removes white halo on Windows desktop icons."""
    rgba = img.convert('RGBA')
    flat = Image.new('RGB', rgba.size, EMERALD_RGB)
    flat.paste(rgba, mask=rgba.split()[3])
    return flat


def _render_master_playwright(root: Path) -> Image.Image:
    from playwright.sync_api import sync_playwright

    size = MASTER_PX
    radius = round(HEADER_RADIUS_PX * size / HEADER_TILE_PX)
    glyph = round(HEADER_GLYPH_PX * size / HEADER_TILE_PX)
    template = _template_path(root).read_text(encoding='utf-8')
    html = (
        template.replace('{{SIZE}}', str(size))
        .replace('{{RADIUS}}', str(radius))
        .replace('{{GLYPH}}', str(glyph))
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': size, 'height': size}, device_scale_factor=1)
        page.set_content(html, wait_until='networkidle')
        page.wait_for_timeout(400)
        png_bytes = page.screenshot(omit_background=False, type='png')
        browser.close()

    master = Image.open(BytesIO(png_bytes))
    return _flatten_emerald(master)


def _downscale(master: Image.Image, size: int) -> Image.Image:
    if master.size[0] == size:
        return master.copy()
    return master.resize((size, size), Image.Resampling.LANCZOS)


def write_icons(root: str | None = None) -> None:
    root_path = Path(root or Path(__file__).resolve().parents[1])
    static_img = root_path / 'static' / 'img'
    connector_dir = root_path / 'connector'
    static_img.mkdir(parents=True, exist_ok=True)
    connector_dir.mkdir(parents=True, exist_ok=True)

    print(f'Rendering login-header icon at {MASTER_PX}px (opaque emerald, no border)...')
    master = _render_master_playwright(root_path)
    icons = [_downscale(master, s) for s in ICO_SIZES]

    master.save(static_img / 'casepm-icon.png', 'PNG')
    icons[ICO_SIZES.index(64)].save(static_img / 'casepm-icon-64.png', 'PNG')

    ico_sizes = [(s, s) for s in ICO_SIZES]
    for ico_path in (static_img / 'casepm-icon.ico', connector_dir / 'casepm-icon.ico'):
        icons[-1].save(ico_path, format='ICO', sizes=ico_sizes, append_images=icons[:-1])

    print(f'Wrote {static_img / "casepm-icon.ico"}')


if __name__ == '__main__':
    write_icons(sys.argv[1] if len(sys.argv) > 1 else None)
