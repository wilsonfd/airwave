# -*- coding: utf-8 -*-
"""Build the app icons from the two supplied artworks.

Dark glass artwork  -> Windows .ico + in-app logo (matches the dark PC UI)
Light glass artwork -> iOS AppIcon + iOS in-app logo

Outputs:
  ios/Sources/Assets.xcassets/AppIcon.appiconset/*.png
  ios/Sources/Assets.xcassets/Logo.imageset/logo.png
  pc/assets/app.ico
  pc/assets/logo.png
  assets/preview_ios.png / preview_ico.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
IOS_ICON_DIR = ROOT / "ios" / "Sources" / "Assets.xcassets" / "AppIcon.appiconset"
IOS_LOGO = ROOT / "ios" / "Sources" / "Assets.xcassets" / "Logo.imageset" / "logo.png"
PC_ASSETS = ROOT / "pc" / "assets"

CANVAS = 1024
CORNER = 0.268  # artwork corner radius / side

# Measured content bounds; height is ~1.3% shorter than width in both files.
DARK = dict(path=ROOT / "assets" / "icon_source.jpg",
            crop=(149, 149, 1899, 1876),
            base=(5, 7, 18), blend=0.35, vignette=0.12)
LIGHT = dict(path=ROOT / "assets" / "icon_light_source.jpg",
             crop=(150, 149, 1898, 1875),
             base=(231, 237, 246), blend=0.08, vignette=0.0)


def rounded_mask(size: int, radius_ratio: float, supersample: int = 4) -> Image.Image:
    big = size * supersample
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(big * radius_ratio)
    draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def load_square(spec: dict) -> Image.Image:
    image = Image.open(spec["path"]).convert("RGB")
    return image.crop(spec["crop"]).resize((CANVAS, CANVAS), Image.LANCZOS)


def make_ios(im: Image.Image, spec: dict) -> Image.Image:
    """Opaque, full-bleed icon: extend the edge colours into the corners."""
    base = spec["base"]
    mask = rounded_mask(CANVAS, CORNER)

    clean = Image.composite(im, Image.new("RGB", im.size, base), mask)
    bg = clean.resize((64, 64), Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
    bg = bg.resize((CANVAS, CANVAS), Image.BICUBIC)
    bg = Image.blend(bg, Image.new("RGB", bg.size, base), spec["blend"])

    feathered = mask.filter(ImageFilter.GaussianBlur(3))
    out = Image.composite(im, bg, feathered)

    if spec["vignette"] > 0:
        vignette = Image.new("L", (CANVAS, CANVAS), 0)
        draw = ImageDraw.Draw(vignette)
        draw.ellipse((-CANVAS * 0.15, -CANVAS * 0.1,
                      CANVAS * 1.15, CANVAS * 1.1), fill=255)
        vignette = vignette.filter(ImageFilter.GaussianBlur(120))
        dark = Image.new("RGB", (CANVAS, CANVAS), (2, 4, 12))
        out = Image.composite(out, Image.blend(out, dark, spec["vignette"]), vignette)

    return out.convert("RGB")


def make_transparent(im: Image.Image, size: int) -> Image.Image:
    mask = rounded_mask(size, CORNER)
    out = im.resize((size, size), Image.LANCZOS).convert("RGBA")
    out.putalpha(mask)
    return out


def save_ico(im: Image.Image) -> None:
    sizes = [256, 128, 64, 48, 40, 32, 24, 20, 16]
    frames = [make_transparent(im, size) for size in sizes]
    frames[0].save(PC_ASSETS / "app.ico", format="ICO",
                   sizes=[(size, size) for size in sizes],
                   append_images=frames[1:])
    frames[1].save(PC_ASSETS / "logo.png")


def main() -> None:
    IOS_ICON_DIR.mkdir(parents=True, exist_ok=True)
    IOS_LOGO.parent.mkdir(parents=True, exist_ok=True)
    PC_ASSETS.mkdir(parents=True, exist_ok=True)

    dark = load_square(DARK)
    light = load_square(LIGHT)

    ios_icon = make_ios(light, LIGHT)
    ios_icon.save(ROOT / "assets" / "preview_ios.png")
    ios_icon.save(IOS_ICON_DIR / "Icon-1024.png")

    slots = [
        ("Icon-20@2x.png", 40), ("Icon-20@3x.png", 60),
        ("Icon-29@2x.png", 58), ("Icon-29@3x.png", 87),
        ("Icon-40@2x.png", 80), ("Icon-40@3x.png", 120),
        ("Icon-60@2x.png", 120), ("Icon-60@3x.png", 180),
    ]
    for name, px in slots:
        ios_icon.resize((px, px), Image.LANCZOS).save(IOS_ICON_DIR / name)

    make_transparent(light, 512).save(IOS_LOGO)

    save_ico(dark)
    make_transparent(dark, 512).save(ROOT / "assets" / "preview_ico.png")
    print("icons written")


if __name__ == "__main__":
    main()
