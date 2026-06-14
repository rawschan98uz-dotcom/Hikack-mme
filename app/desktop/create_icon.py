"""Generate Hi Jack LMS desktop icon (lms.ico)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'assets' / 'lms.ico'


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r'C:\Windows\Fonts\segoeuib.ttf'),
        Path(r'C:\Windows\Fonts\arialbd.ttf'),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_icon(size: int) -> Image.Image:
    img = Image.new('RGBA', (size, size), (37, 99, 235, 255))
    draw = ImageDraw.Draw(img)

    margin = max(8, size // 16)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=max(12, size // 8),
        fill=(59, 130, 246, 255),
    )

    font_size = max(14, size // 4)
    font = load_font(font_size)
    text = 'LMS'
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((size - tw) // 2, (size - th) // 2 - max(1, size // 64)),
        text,
        fill='white',
        font=font,
    )
    return img


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    base = draw_icon(256)
    base.save(
        OUT,
        format='ICO',
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    print(f'Icon saved: {OUT}')


if __name__ == '__main__':
    main()
