"""Generate Case PM desktop icon — solid emerald squircle + white hard hat."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

MASTER_PX = 1024
SQUIRCLE_RADIUS_PCT = 0.22
GLYPH_PCT = 0.43
EMERALD_RGB = (5, 150, 105)
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
OUTPUT_STEM = 'casepm-desktop-icon'


def _template_path(root: Path) -> Path:
    return root / 'scripts' / 'casepm-icon-template.html'


def _flatten_emerald(img: Image.Image) -> Image.Image:
    rgba = img.convert('RGBA')
    flat = Image.new('RGB', rgba.size, EMERALD_RGB)
    flat.paste(rgba, mask=rgba.split()[3])
    return flat


def _render_master_playwright(root: Path) -> Image.Image:
    from playwright.sync_api import sync_playwright

    size = MASTER_PX
    radius = round(size * SQUIRCLE_RADIUS_PCT)
    glyph = round(size * GLYPH_PCT)
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

    return _flatten_emerald(Image.open(BytesIO(png_bytes)))


def write_icons(root: str | None = None) -> None:
    root_path = Path(root or Path(__file__).resolve().parents[1])
    static_img = root_path / 'static' / 'img'
    connector_dir = root_path / 'connector'
    static_img.mkdir(parents=True, exist_ok=True)
    connector_dir.mkdir(parents=True, exist_ok=True)

    print(f'Rendering {OUTPUT_STEM} at {MASTER_PX}px...')
    master = _render_master_playwright(root_path)
    icons = [master.resize((s, s), Image.Resampling.LANCZOS) for s in ICO_SIZES]

    master.save(static_img / f'{OUTPUT_STEM}.png', 'PNG')
    icons[ICO_SIZES.index(64)].save(static_img / f'{OUTPUT_STEM}-64.png', 'PNG')

    ico_sizes = [(s, s) for s in ICO_SIZES]
    for folder in (static_img, connector_dir):
        icons[-1].save(
            folder / f'{OUTPUT_STEM}.ico',
            format='ICO',
            sizes=ico_sizes,
            append_images=icons[:-1],
        )

    # Legacy filenames used by favicon / older connectors
    master.save(static_img / 'casepm-icon.png', 'PNG')
    icons[-1].save(static_img / 'casepm-icon.ico', format='ICO', sizes=ico_sizes, append_images=icons[:-1])
    icons[-1].save(connector_dir / 'casepm-icon.ico', format='ICO', sizes=ico_sizes, append_images=icons[:-1])
    print('Wrote desktop icon assets')


if __name__ == '__main__':
    write_icons(sys.argv[1] if len(sys.argv) > 1 else None)
