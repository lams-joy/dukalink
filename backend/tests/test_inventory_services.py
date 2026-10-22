from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction

from apps.catalog.models import ProductUnit
from apps.common.exceptions import (
    DomainError,
    InsufficientStock,
    InvalidQuantity,
    InvalidUnit,
    ProductNotTracked,
    StateConflict,
)
from apps.inventory import services
from apps.inventory.models import (
    AppendOnlyError,
    MovementType,
    Sale,
    StockMovement,
)

pytestmark = pytest.mark.django_db

D = Decimal


def receive_sack(shop, user, sugar, quantity="1"):
    return services.record_purchase_receipt(
        shop=shop,
        user=user,
        items=[
            {
                "product_id": sugar.product.pk,
                "product_unit_id": sugar.sack.pk,
                "quantity": D(quantity),
                "unit_cost": D("7000.00"),
            }
        ],
        supplier_name="Example Wholesale",
    )


def sell_kg(shop, user, tracked, sugar, quantity, price="180.00"):
    return services.record_sale(
        shop=shop,
        user=user,
        items=[
            {
                "shop_product_id": tracked.pk,
                "product_unit_id": sugar.kg.pk,
                "quantity": D(quantity),
                "unit_price": D(price),
            }
        ],
    )


def test_a_50kg_sack_adds_50kg_and_a_1_5kg_sale_subtracts_1_5kg(shop, owner, sugar, tracked_sugar):
    receipt = receive_sack(shop, owner, sugar)
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")
    assert receipt.total_cost == D("7000.00")

    sale = sell_kg(shop, owner, tracked_sugar, sugar, "1.5")
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("48.5")
    assert sale.total_amount == D("270.00")

    movements = list(tracked_sugar.movements.order_by("created_at"))
    assert [m.quantity_base_delta for m in movements] == [D("50"), D("-1.5")]
    assert [m.balance_after_base for m in movements] == [D("50"), D("48.5")]
    # The unit that was entered is snapshotted on the movement.
    assert movements[0].entered_unit_name == "50 kg sack"
    assert movements[0].entered_unit_base_quantity == D("50")
    assert movements[0].unit_cost_base == D("140.000000")  # 7000 / 50 per kg


def test_cached_balance_reconciles_with_ledger(shop, owner, sugar, tracked_sugar):
    receive_sack(shop, owner, sugar, "2")
    sell_kg(shop, owner, tracked_sugar, sugar, "10.25")
    sell_kg(shop, owner, tracked_sugar, sugar, "0.75")
    services.record_adjustment(
        shop=shop, user=owner, shop_product_id=tracked_sugar.pk, delta_base=D("-3"), reason="spillage"
    )
    tracked_sugar.refresh_from_db()
    ledger = sum(m.quantity_base_delta for m in tracked_sugar.movements.all())
    assert tracked_sugar.quantity_base == ledger == D("86")


def test_overselling_is_rejected_and_writes_nothing(shop, owner, sugar, tracked_sugar):
    receive_sack(shop, owner, sugar)
    with pytest.raises(InsufficientStock):
        sell_kg(shop, owner, tracked_sugar, sugar, "60")
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")
    assert tracked_sugar.movements.count() == 1
    assert Sale.objects.count() == 0  # the whole operation rolled back


def test_a_multi_line_sale_is_all_or_nothing(shop, owner, sugar, flour, tracked_sugar):
    tracked_flour = services.track_product(shop=shop, product_id=flour.product.pk)
    receive_sack(shop, owner, sugar)
    with pytest.raises(InsufficientStock):
        services.record_sale(
            shop=shop,
            user=owner,
            items=[
                {"shop_product_id": tracked_sugar.pk, "product_unit_id": sugar.kg.pk,
                 "quantity": D("5"), "unit_price": D("180")},
                {"shop_product_id": tracked_flour.pk, "product_unit_id": flour.kg.pk,
                 "quantity": D("1"), "unit_price": D("120")},  # flour has no stock
            ],
        )  # fmt: skip
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")


def test_unit_must_belong_to_the_product(shop, owner, sugar, flour, tracked_sugar):
    receive_sack(shop, owner, sugar)
    with pytest.raises(InvalidUnit):
        sell_kg(shop, owner, tracked_sugar, flour, "1")  # flour's kg unit on sugar


def test_over_precise_quantities_are_rejected(shop, owner, sugar, tracked_sugar):
    third = ProductUnit.objects.create(
        product=sugar.product, unit_name="third", base_quantity=D("0.333333")
    )
    receive_sack(shop, owner, sugar)
    with pytest.raises(InvalidQuantity):
        services.record_sale(
            shop=shop, user=owner,
            items=[{"shop_product_id": tracked_sugar.pk, "product_unit_id": third.pk,
                    "quantity": D("1.5"), "unit_price": D("10")}],
        )  # fmt: skip


def test_untracked_or_other_shop_product_is_rejected(shop, other_shop, owner, other_user, sugar):
    theirs = services.track_product(shop=other_shop, product_id=sugar.product.pk)
    with pytest.raises(ProductNotTracked):
        services.record_sale(
            shop=shop, user=owner,
            items=[{"shop_product_id": theirs.pk, "product_unit_id": sugar.kg.pk,
                    "quantity": D("1"), "unit_price": D("10")}],
        )  # fmt: skip
    with pytest.raises(ProductNotTracked):
        receive_sack(shop, owner, sugar)  # sugar is not tracked in `shop`


def test_tracking_the_same_product_twice_is_a_conflict(shop, sugar, tracked_sugar):
    with pytest.raises(StateConflict):
        services.track_product(shop=shop, product_id=sugar.product.pk)


def test_opening_stock_only_once_and_only_before_other_movements(shop, owner, sugar, tracked_sugar):
    services.record_opening_stock(
        shop=shop, user=owner, shop_product_id=tracked_sugar.pk, unit_id=sugar.kg.pk, quantity=D("12")
    )
    with pytest.raises(StateConflict):
        services.record_opening_stock(
            shop=shop, user=owner, shop_product_id=tracked_sugar.pk, unit_id=sugar.kg.pk,
            quantity=D("5"),
        )
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("12")
    assert tracked_sugar.movements.get().movement_type == MovementType.OPENING_STOCK


def test_adjustments_need_a_reason_and_cannot_go_below_zero(shop, owner, sugar, tracked_sugar):
    receive_sack(shop, owner, sugar)
    with pytest.raises(DomainError):
        services.record_adjustment(
            shop=shop, user=owner, shop_product_id=tracked_sugar.pk, delta_base=D("-1"), reason="  "
        )
    with pytest.raises(InsufficientStock):
        services.record_adjustment(
            shop=shop, user=owner, shop_product_id=tracked_sugar.pk, delta_base=D("-51"), reason="x"
        )


def test_reversal_restores_stock_once_only(shop, owner, sugar, tracked_sugar):
    receive_sack(shop, owner, sugar)
    sell_kg(shop, owner, tracked_sugar, sugar, "10")
    sale_movement = tracked_sugar.movements.get(movement_type=MovementType.SALE)

    reversal = services.reverse_movement(
        shop=shop, user=owner, movement_id=sale_movement.pk, reason="entered by mistake"
    )
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")
    assert reversal.reference_id == sale_movement.pk

    with pytest.raises(StateConflict):  # already reversed
        services.reverse_movement(shop=shop, user=owner, movement_id=sale_movement.pk)
    with pytest.raises(StateConflict):  # a reversal cannot be reversed
        services.reverse_movement(shop=shop, user=owner, movement_id=reversal.pk)
    with pytest.raises(DomainError):  # unknown movement
        services.reverse_movement(shop=shop, user=owner, movement_id=uuid4())


def test_ledger_rows_are_append_only(shop, owner, sugar, tracked_sugar):
    receive_sack(shop, owner, sugar)
    movement = tracked_sugar.movements.get()
    movement.note = "edited"
    with pytest.raises(AppendOnlyError):
        movement.save()
    with pytest.raises(AppendOnlyError):
        movement.delete()


def test_database_rejects_a_sale_movement_with_a_positive_delta(owner, tracked_sugar):
    with pytest.raises(IntegrityError), transaction.atomic():
        StockMovement.objects.create(
            shop_product=tracked_sugar,
            movement_type=MovementType.SALE,
            quantity_base_delta=D("5"),
            balance_after_base=D("5"),
            created_by=owner,
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL row locking")
def test_concurrent_sales_cannot_oversell(shop, owner, sugar, tracked_sugar):
    import threading

    receive_sack(shop, owner, sugar)  # 50 kg
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def attempt():
        try:
            barrier.wait()
            sell_kg(shop, owner, tracked_sugar, sugar, "30")
            outcomes.append("sold")
        except InsufficientStock:
            outcomes.append("rejected")
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == ["rejected", "sold"]
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("20")
