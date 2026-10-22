"""Read-only reporting queries. Quantities are base units; money is the shop's currency."""

import zoneinfo
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum

from .models import PurchaseItem, SaleItem, ShopProduct

MAX_SPAN_DAYS = 366
DEFAULT_SPAN_DAYS = 30


def period_bounds(shop, date_from: date | None, date_to: date | None):
    """Inclusive local dates in the shop's timezone -> [start, end) aware datetimes."""
    tz = zoneinfo.ZoneInfo(shop.timezone)
    today = datetime.now(tz).date()
    date_to = date_to or today
    date_from = date_from or (date_to - timedelta(days=DEFAULT_SPAN_DAYS - 1))
    start = datetime.combine(date_from, time.min, tzinfo=tz)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    return date_from, date_to, start, end


def low_stock_queryset(shop):
    return (
        ShopProduct.objects.filter(
            shop=shop, is_active=True, reorder_level_base__isnull=False,
            quantity_base__lte=F("reorder_level_base"),
        )
        .select_related("product")
        .annotate(gap=F("quantity_base") - F("reorder_level_base"))
        .order_by("gap", "product__name")
    )  # fmt: skip


def _money(value) -> str:
    return f"{(value or Decimal('0')):.2f}"


def _qty(value) -> str:
    return f"{(value or Decimal('0')):.6f}"


def summary(shop, date_from, date_to, *, top_n: int = 5) -> dict:
    date_from, date_to, start, end = period_bounds(shop, date_from, date_to)

    tracked = ShopProduct.objects.filter(shop=shop, is_active=True)
    stock = {
        "tracked_products": tracked.count(),
        "low_stock_count": low_stock_queryset(shop).count(),
        "out_of_stock_count": tracked.filter(quantity_base__lte=0).count(),
    }

    # Only live lines count: a reversed line is excluded, so a fully voided sale or receipt
    # disappears from the totals and a partly reversed one counts only what still stands.
    sale_lines = SaleItem.objects.filter(
        sale__shop=shop, sale__sold_at__gte=start, sale__sold_at__lt=end, reversed_at__isnull=True
    )
    sales_agg = sale_lines.aggregate(count=Count("sale_id", distinct=True), total=Sum("line_total"))

    purchase_lines = PurchaseItem.objects.filter(
        receipt__shop=shop,
        receipt__received_at__gte=start,
        receipt__received_at__lt=end,
        reversed_at__isnull=True,
    )
    purchases_agg = purchase_lines.aggregate(
        count=Count("receipt_id", distinct=True), total=Sum("line_total")
    )

    top = (
        sale_lines.values("shop_product_id", "product_name_snapshot")
        .annotate(qty=Sum("quantity_base"), revenue=Sum("line_total"))
        .order_by("-revenue", "product_name_snapshot")[:top_n]
    )

    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat(), "timezone": shop.timezone},
        "stock": stock,
        "sales": {"count": sales_agg["count"], "total_amount": _money(sales_agg["total"])},
        "purchases": {"count": purchases_agg["count"], "total_cost": _money(purchases_agg["total"])},
        "top_selling": [
            {
                "shop_product_id": str(row["shop_product_id"]),
                "product_name": row["product_name_snapshot"],
                "quantity_base": _qty(row["qty"]),
                "revenue": _money(row["revenue"]),
            }
            for row in top
        ],
    }
