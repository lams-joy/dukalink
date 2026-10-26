"""Kept for older instructions: same as `seed_catalog`."""
from .seed_catalog import Command as SeedCatalogCommand


class Command(SeedCatalogCommand):
    help = "Alias of seed_catalog (loads the bundled duka product list)."
