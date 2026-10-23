from django.core.management.base import BaseCommand

from apps.groupbuying import services


class Command(BaseCommand):
    help = (
        "Close or fail every open group order whose deadline has passed. Safe to run at any "
        "time and as often as you like (groups are also settled lazily when read). "
        "Suggested: cron every 5 minutes."
    )

    def handle(self, *args, **options):
        settled = services.close_expired_groups()
        self.stdout.write(f"Settled {settled} expired group order(s).")
