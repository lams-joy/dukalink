"""Load the shared catalogue from a CSV file (safe to run repeatedly).

Edit apps/catalog/seed/duka_catalog.csv (any spreadsheet app can open it) and run:
    python manage.py seed_catalog                 # default file
    python manage.py seed_catalog --file my.csv   # your own file

Columns: name, brand, category, base_unit, units
`units` is a list separated by "|", each written "label=factor", where factor is how many
base units one of that unit contains, e.g.  50 kg sack=50|2 kg packet=2
Existing products are left alone (their units are topped up); nothing is deleted.
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Product, ProductUnit

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "seed" / "duka_catalog.csv"


def parse_units(text: str, line: int) -> list[tuple[str, Decimal]]:
    out = []
    for part in filter(None, (p.strip() for p in text.split("|"))):
        label, sep, factor = part.rpartition("=")
        if not sep or not label.strip():
            raise CommandError(f"Line {line}: unit '{part}' must look like 'label=factor'.")
        try:
            value = Decimal(factor.strip())
        except InvalidOperation:
            raise CommandError(f"Line {line}: '{factor}' is not a number.") from None
        if value <= 0:
            raise CommandError(f"Line {line}: factor for '{label}' must be above zero.")
        out.append((label.strip(), value))
    return out


class Command(BaseCommand):
    help = "Load or top up the shared product catalogue from a CSV file (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE), help="CSV path (default: the bundled duka list)")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        created = topped_up = 0
        with path.open(newline="", encoding="utf-8-sig") as fh:
            for line, row in enumerate(csv.DictReader(fh), start=2):
                name, base_unit = (row.get("name") or "").strip(), (row.get("base_unit") or "").strip()
                if not name or not base_unit:
                    raise CommandError(f"Line {line}: name and base_unit are required.")
                brand = (row.get("brand") or "").strip()
                product = Product.objects.filter(owner_shop__isnull=True, name__iexact=name, brand__iexact=brand).first()
                if product is None:
                    product = Product.objects.create(
                        name=name, brand=brand, category=(row.get("category") or "").strip(), base_unit=base_unit)
                    created += 1
                product.ensure_base_unit()
                for label, factor in parse_units(row.get("units") or "", line):
                    _, new = ProductUnit.objects.get_or_create(
                        product=product, unit_name=label,
                        defaults={"base_quantity": factor, "is_purchase_unit": True, "is_sale_unit": True})
                    topped_up += new
        self.stdout.write(self.style.SUCCESS(f"Catalogue ready: {created} new products, {topped_up} new units."))
