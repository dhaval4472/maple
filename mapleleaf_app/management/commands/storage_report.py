from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from mapleleaf_app.models import PhotoRequest


def folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class Command(BaseCommand):
    help = "Show the disk footprint of the database, static files and uploaded media."

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        rows = [
            ("Database", Path(settings.DATABASES["default"]["NAME"])),
            ("Static source", base / "static"),
            ("Collected static", base / "staticfiles"),
            ("Uploaded media", Path(settings.MEDIA_ROOT)),
        ]
        for label, path in rows:
            self.stdout.write(f"{label:<18} {human(folder_size(path)):>10}  {path}")

        self.stdout.write(f"\nPhoto requests stored: {PhotoRequest.objects.count()}")
        oldest = PhotoRequest.objects.order_by("retention_expires_at").first()
        if oldest and oldest.retention_expires_at:
            self.stdout.write(f"Next retention date: {oldest.retention_expires_at}")
