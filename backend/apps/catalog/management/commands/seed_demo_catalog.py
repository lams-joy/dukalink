from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Product, ProductUnit

DEMO = [
    ("Sugar", "kg", "Staples", [("50 kg sack", "50"), ("2 kg packet", "2")]),
    ("Maize flour", "kg", "Staples", [("24 x 2 kg carton", "48"), ("2 kg packet", "2")]),
    ("Cooking oil", "litre", "Staples", [("20 litre jerrycan", "20"), ("500 ml bottle", "0.5")]),
    ("Bar soap", "piece", "Household", [("carton of 24", "24")]),
]


class Command(BaseCommand):
    help = "Create a few demo catalogue products with unit conversions (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        for name, base_unit, category, units in DEMO:
            product, _ = Product.objects.get_or_create(
                name=name, defaults={"base_unit": base_unit, "category": category}
            )
            product.ensure_base_unit()
            for unit_name, factor in units:
                ProductUnit.objects.get_or_create(
                    product=product,
                    unit_name=unit_name,
                    defaults={
                        "base_quantity": Decimal(factor),
                        "is_purchase_unit": True,
                        "is_sale_unit": True,
                    },
                )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(DEMO)} products."))
