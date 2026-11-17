"""Image preparation helpers for user uploads.

Phone photos are commonly 3–8 MB. The site only needs enough detail to assess
damage, so uploads are rotated, stripped of metadata, bounded in pixel size and
re-encoded as WebP before they are stored. That keeps media growth predictable
on a small host without asking visitors to resize their own photos.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

DEFAULT_MAX_DIMENSION = 1600
DEFAULT_QUALITY = 82


def optimize_photo_upload(upload, max_dimension=None, quality=None):
    """Return a compressed, orientation-corrected WebP ContentFile."""
    max_dimension = max_dimension or getattr(settings, "PHOTO_MAX_DIMENSION", DEFAULT_MAX_DIMENSION)
    quality = quality or getattr(settings, "PHOTO_WEBP_QUALITY", DEFAULT_QUALITY)

    upload.seek(0)
    with Image.open(upload) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")

        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, "WEBP", quality=quality, method=6)

    stem = Path(getattr(upload, "name", "photo")).stem[:60] or "photo"
    return ContentFile(buffer.getvalue(), name=f"{stem}.webp")
