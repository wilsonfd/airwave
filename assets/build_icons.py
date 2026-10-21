# -*- coding: utf-8 -*-
"""Build all app icons from the supplied artwork.

Source: assets/icon_source.jpg (2048x2048, rounded square on white).

Outputs:
  ios/Sources/Assets.xcassets/AppIcon.appiconset/*.png  (opaque, full-bleed)
  pc/assets/app.ico                                     (transparent rounded square)
  pc/assets/logo.png                                    (transparent, 256px)
  assets/preview_ios.png / preview_ico.png
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "icon_source.jpg"
IOS_ICON_DIR = ROOT / "ios" / "Sources" / "Assets.xcassets" / "AppIcon.appiconset"
PC_ASSETS = ROOT / "pc" / "assets"

# Content bounds measured from the source. Height is 1.3% shorter than width;
# normalising to a square is imperceptible and gives a clean icon.
CROP = (149, 149, 1899, 1876)
CANVAS = 1024
CORNER = 0.268  # artwork corner radius / side


def rounded_mask(size: int, radius_ratio: float, supersample: int = 4) -> Image.Image:
    big = size * supersample
    m = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(m)
    r = int(big * radius_ratio)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=r, fill=255)
    return m.resize((size, size), Image.LANCZOS)


def crop_square() -> Image.Image:
    im = Image.open(SRC).convert("RGB")
    im = im.crop(CROP).resize((CANVAS, CANVAS), Image.LANCZOS)
    return im


def make_ios(im: Image.Image) -> Image.Image:
    """Full-bleed opaque icon: blurred colour extension into the corners."""
    mask = rounded_mask(CANVAS, CORNER)
    # Remove the white paper corners before deriving the colour field, otherwise
    # the extension turns grey.
    clean = Image.composite(im, Image.new("RGB", im.size, (5, 7, 18)), mask)
    bg = clean.resize((64, 64), Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
    bg = bg.resize((CANVAS, CANVAS), Image.BICUBIC)
    # Slightly darken so the extension reads as a shadow/glow, not a seam.
    bg = Image.blend(bg, Image.new("RGB", bg.size, (5, 7, 18)), 0.35)

    # Feather the composite boundary so no hard seam is visible.
    mask = mask.filter(ImageFilter.GaussianBlur(3))
    out = Image.composite(im, bg, mask)

    # Very subtle inner vignette to add depth.
    vignette = Image.new("L", (CANVAS, CANVAS), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse((-CANVAS * 0.15, -CANVAS * 0.1, CANVAS * 1.15, CANVAS * 1.1), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGB", (CANVAS, CANVAS), (2, 4, 12))
    out = Image.composite(out, Image.blend(out, dark, 0.12), vignette)
    return out.convert("RGB")


def make_transparent(im: Image.Image, size: int) -> Image.Image:
    mask = rounded_mask(size, CORNER)
    small = im.resize((size, size), Image.LANCZOS)
    out = small.convert("RGBA")
    out.putalpha(mask)
    return out


def save_ico(im: Image.Image) -> None:
    # Build each size separately so small sizes stay crisp.
    sizes = [256, 128, 64, 48, 40, 32, 24, 20, 16]
    frames = [make_transparent(im, s) for s in sizes]
    base = frames[0]
    base.save(PC_ASSETS / "app.ico", format="ICO",
              sizes=[(s, s) for s in sizes], append_images=frames[1:])
    frames[1].save(PC_ASSETS / "logo.png")


def main() -> None:
    IOS_ICON_DIR.mkdir(parents=True, exist_ok=True)
    PC_ASSETS.mkdir(parents=True, exist_ok=True)
    im = crop_square()
    ios = make_ios(im)
    ios.save(ROOT / "assets" / "preview_ios.png")
    ios.save(IOS_ICON_DIR / "Icon-1024.png")

    # Standard iOS app icon slots (iOS 15 compatible, no alpha).
    slots = [
        ("Icon-20@2x.png", 40), ("Icon-20@3x.png", 60),
        ("Icon-29@2x.png", 58), ("Icon-29@3x.png", 87),
        ("Icon-40@2x.png", 80), ("Icon-40@3x.png", 120),
        ("Icon-60@2x.png", 120), ("Icon-60@3x.png", 180),
        ("Icon-76@1x.png", 76), ("Icon-76@2x.png", 152),
        ("Icon-83.5@2x.png", 167),
    ]
    for name, px in slots:
        ios.resize((px, px), Image.LANCZOS).save(IOS_ICON_DIR / name)

    save_ico(im)
    make_transparent(im, 512).save(ROOT / "assets" / "preview_ico.png")
    print("icons written")


if __name__ == "__main__":
    main()
