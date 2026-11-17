#!/usr/bin/env python3
"""Convert the large bundled images to WebP for a smaller deployment.

Run this after replacing one of the source images. The generated `.webp`
files are what the templates reference; originals can be archived outside
`static/` so they are not uploaded to the production host.

Usage:
    python scripts/optimize_static_images.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

# (source, quality) — illustrations tolerate a lower quality than text-heavy
# accreditation marks, so the marks keep a higher setting.
IMAGES = (
    ("static/img/package/car-repair.png", 82),
    ("static/img/package/car-repair-1.png", 82),
    ("static/img/package/car-on-lift.png", 82),
    ("static/img/package/painting.png", 82),
    ("static/img/package/accredit.png", 88),
    ("static/img/hero-poster.jpg", 82),
    ("static/img/hero-poster-mobile.jpg", 82),
)


def convert(relative_path: str, quality: int) -> None:
    source = ROOT / relative_path
    if not source.exists():
        print(f"skip (missing): {relative_path}")
        return

    output = source.with_suffix(".webp")
    image = Image.open(source)
    if image.mode in ("P", "LA"):
        image = image.convert("RGBA")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    image.save(output, "WEBP", quality=quality, method=6)
    before = source.stat().st_size
    after = output.stat().st_size
    print(
        f"{relative_path} -> {output.relative_to(ROOT)} "
        f"({before / 1024:.0f} KB -> {after / 1024:.0f} KB)"
    )


def main() -> None:
    for relative_path, quality in IMAGES:
        convert(relative_path, quality)


if __name__ == "__main__":
    main()
