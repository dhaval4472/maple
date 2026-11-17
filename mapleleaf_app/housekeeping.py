"""Small maintenance jobs that keep SQLite and the media folder from growing."""

from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone

from .models import PhotoRequest

PRUNE_BATCH_SIZE = 50


def prune_expired_photo_requests(limit: int = PRUNE_BATCH_SIZE) -> tuple[int, int]:
    """Delete expired photo requests and their image files.

    Django does not remove files when a model row is deleted, so the file is
    removed explicitly first. The limit keeps a request-triggered cleanup short.
    """
    expired = (
        PhotoRequest.objects.filter(retention_expires_at__lt=timezone.localdate())
        .prefetch_related("photos")[:limit]
    )
    deleted = 0
    files = 0
    for request in expired:
        for photo in request.photos.all():
            if photo.image:
                photo.image.delete(save=False)
                files += 1
        request.delete()
        deleted += 1
    return deleted, files


def maybe_prune_expired_photo_requests() -> None:
    """Run the cleanup at most once per day without requiring a cron daemon."""
    key = f"maple-leaf:photo-prune:{timezone.localdate().isoformat()}"
    if cache.get(key):
        return
    cache.set(key, True, 60 * 60 * 24)
    try:
        prune_expired_photo_requests()
    except Exception:
        # Housekeeping must never break a visitor's submission.
        cache.delete(key)
