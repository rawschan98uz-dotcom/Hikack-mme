"""Build PNG + mask PNG for sidebar icons from source SVG/PNG in public/icons/."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / 'public' / 'icons'
NAMES = ('teacher', 'rating', 'finance', 'settings')


def svg_to_png(svg: Path, png: Path, size: int = 256) -> None:
    cmd = [
        'ffmpeg',
        '-y',
        '-i',
        str(svg),
        '-vf',
        f'scale={size}:{size}:force_original_aspect_ratio=decrease,pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:white',
        str(png),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def mask_from_dark(path: Path, out: Path, lum_threshold: int = 140) -> None:
    img = Image.open(path).convert('RGBA')
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            lum = (r + g + b) / 3
            if a >= 20 and lum <= lum_threshold:
                px[x, y] = (255, 255, 255, 255)
            else:
                px[x, y] = (0, 0, 0, 0)
    img.save(out)


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        svg = ICONS / f'{name}.svg'
        png = ICONS / f'{name}.png'
        mask = ICONS / f'{name}-mask.png'

        if svg.is_file() and not png.is_file():
            svg_to_png(svg, png)
        elif not png.is_file():
            print(f'skip {name}: no source', file=sys.stderr)
            continue

        mask_from_dark(png, mask)
        print(f'ok {name}: {png.name}, {mask.name}')


if __name__ == '__main__':
    main()
