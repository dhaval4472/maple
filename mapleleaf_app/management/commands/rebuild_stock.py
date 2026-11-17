"""Recalculate cached stock balances from the movement ledger."""

from django.core.management.base import BaseCommand

from mapleleaf_app.inventory import rebuild_stock_balances


class Command(BaseCommand):
    help = "Recheck every part's cached stock balance against its movements."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        changes = rebuild_stock_balances(dry_run=dry_run)

        if not changes:
            self.stdout.write(self.style.SUCCESS("All stock balances match the ledger."))
            return

        for part, old_balance, new_balance in changes:
            if dry_run:
                self.stdout.write(
                    f"Would correct {part.sku}: {old_balance} -> {new_balance}"
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Corrected {part.sku}: {old_balance} -> {new_balance}"
                    )
                )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(changes)} part(s) would be corrected. Run without --dry-run to apply."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Corrected {len(changes)} part(s).")
            )
