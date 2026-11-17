from django.core.management.base import BaseCommand

from mapleleaf_app.housekeeping import prune_expired_photo_requests


class Command(BaseCommand):
    help = "Delete photo requests past their retention date, including image files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum number of expired requests to remove in one run (default: 500).",
        )

    def handle(self, *args, **options):
        deleted, files = prune_expired_photo_requests(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"Removed {deleted} expired photo request(s) and {files} image file(s).")
        )
