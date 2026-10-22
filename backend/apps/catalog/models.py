import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class Product(models.Model):
    """A product. owner_shop is NULL for the shared catalogue; a custom product belongs to,
    and is visible only to, the one shop that created it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=32, blank=True)
    category = models.CharField(max_length=100, blank=True)
    base_unit = models.CharField(max_length=50, help_text="Canonical unit, e.g. kg, litre, piece.")
    owner_shop = models.ForeignKey(
        "shops.Shop", null=True, blank=True, on_delete=models.PROTECT, related_name="custom_products"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["name"])]
        constraints = [
            # A shop cannot hold two custom products with the same name + brand.
            models.UniqueConstraint(
                "owner_shop", Lower("name"), Lower("brand"),
                condition=Q(owner_shop__isnull=False, is_active=True),
                name="uniq_custom_product_per_shop",
            ),
        ]  # fmt: skip

    def ensure_base_unit(self) -> "ProductUnit":
        unit, _ = ProductUnit.objects.get_or_create(
            product=self,
            unit_name=self.base_unit,
            defaults={
                "base_quantity": Decimal("1"),
                "is_purchase_unit": True,
                "is_sale_unit": True,
            },
        )
        return unit

    def __str__(self):
        return self.name


class ProductUnit(models.Model):
    """A unit a product can be bought/sold in, with its conversion to the base unit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="units")
    unit_name = models.CharField(max_length=50)  # e.g. "kg", "50 kg sack"
    base_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    is_purchase_unit = models.BooleanField(default=True)
    is_sale_unit = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "unit_name"], name="uniq_unit_per_product"),
            models.CheckConstraint(
                condition=Q(base_quantity__gt=0), name="productunit_base_quantity_positive"
            ),
        ]

    def clean(self):
        super().clean()
        if self.base_quantity is not None and self.base_quantity <= 0:
            raise ValidationError({"base_quantity": "Conversion factor must be positive."})
        if (
            self.product_id
            and self.unit_name == self.product.base_unit
            and self.base_quantity != Decimal("1")
        ):
            raise ValidationError({"base_quantity": "The base unit must have a factor of 1."})

    def __str__(self):
        return f"{self.unit_name} = {self.base_quantity} {self.product.base_unit}"
