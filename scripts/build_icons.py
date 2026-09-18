"""Generate the app icons every platform wants, from the NavPort logo mark.

Development-only tool. Pillow is deliberately not in requirements.txt — the
icons are committed to the repo, so the production image never needs it:

    python -m pip install pillow
    python scripts/build_icons.py

Three shapes get produced, because the platforms genuinely want different
things:

  any        The mark on its solid brand tile, edge to edge. What a browser
             tab or a desktop shortcut shows.
  maskable   The same mark inset into the centre 60%, on a full-bleed
             background. Android crops icons to whatever shape the launcher
             uses — circle, squircle, rounded square — and anything outside
             that safe zone is liable to be cut off. An `any` icon used as a
             maskable one gets its points clipped.
  apple      Square with no transparency. iOS applies its own rounding and
             renders transparency as black.
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow is required: python -m pip install pillow", file=sys.stderr)
    sys.exit(1)

OUT = Path(__file__).resolve().parent.parent / "frontend" / "assets" / "icons"

BRAND = (27, 74, 124)          # --accent  #1B4A7C
MARK = (255, 255, 255)

# The logo path from index.html, as its polygon points in the original 24x24
# viewBox. Keep these in step with the <svg> in the markup.
MARK_POINTS = [
    (12.0, 2.6), (20.4, 19.0), (19.2, 20.0),
    (12.0, 16.0), (4.8, 20.0), (3.6, 19.0),
]
VIEWBOX = 24.0

# Rendered at 4x and downsampled, since ImageDraw.polygon has no antialiasing
# of its own and the mark is all diagonals.
SUPERSAMPLE = 4


def render(size: int, *, inset: float = 1.0, background=BRAND) -> Image.Image:
    """The mark centred on a tile, occupying `inset` of the available width."""
    canvas = size * SUPERSAMPLE
    image = Image.new("RGB", (canvas, canvas), background)
    draw = ImageDraw.Draw(image)

    scale = canvas / VIEWBOX * inset
    offset = (canvas - VIEWBOX * scale) / 2

    draw.polygon([(x * scale + offset, y * scale + offset) for x, y in MARK_POINTS], fill=MARK)

    return image.resize((size, size), Image.LANCZOS)


def save(image: Image.Image, name: str) -> None:
    path = OUT / name
    image.save(path, "PNG", optimize=True)
    print(f"  {name:28s} {path.stat().st_size / 1024:6.1f} KB")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    print("Standard icons (purpose: any)")
    for size in (48, 72, 96, 128, 144, 192, 256, 384, 512):
        save(render(size, inset=0.62), f"icon-{size}.png")

    print("\nMaskable icons (purpose: maskable — mark inside the 60% safe zone)")
    for size in (192, 512):
        save(render(size, inset=0.42), f"maskable-{size}.png")

    print("\nApple touch icon")
    save(render(180, inset=0.62), "apple-touch-icon.png")

    print("\nFavicons")
    for size in (16, 32):
        save(render(size, inset=0.70), f"favicon-{size}.png")

    # A single .ico holding both sizes, for browsers that still ask for one.
    ico = OUT / "favicon.ico"
    render(32, inset=0.70).save(ico, sizes=[(16, 16), (32, 32)])
    print(f"  {'favicon.ico':28s} {ico.stat().st_size / 1024:6.1f} KB")

    print(f"\nWrote {len(list(OUT.iterdir()))} files to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
