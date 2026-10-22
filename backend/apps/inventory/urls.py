from django.urls import path

from . import views

S = "shops/<uuid:shop_id>/"

urlpatterns = [
    path(f"{S}inventory/", views.InventoryListCreateView.as_view(), name="inventory-list"),
    path(f"{S}inventory/<uuid:item_id>/", views.InventoryDetailView.as_view(), name="inventory-detail"),
    path(
        f"{S}inventory/<uuid:item_id>/settings/",
        views.InventorySettingsView.as_view(),
        name="inventory-settings",
    ),
    path(
        f"{S}inventory/<uuid:item_id>/opening-stock/",
        views.OpeningStockView.as_view(),
        name="inventory-opening-stock",
    ),
    path(f"{S}stock-adjustments/", views.StockAdjustmentView.as_view(), name="stock-adjustments"),
    path(f"{S}purchase-receipts/", views.PurchaseReceiptView.as_view(), name="purchase-receipts"),
    path(f"{S}sales/", views.SaleView.as_view(), name="sales"),
    path(f"{S}stock-movements/", views.StockMovementListView.as_view(), name="stock-movements"),
    path(
        f"{S}stock-movements/<uuid:movement_id>/reverse/",
        views.StockReversalView.as_view(),
        name="stock-movement-reverse",
    ),
    path(f"{S}stock-counts/", views.StockCountListCreateView.as_view(), name="stock-counts"),
    path(
        f"{S}stock-counts/<uuid:count_id>/",
        views.StockCountDetailView.as_view(),
        name="stock-count-detail",
    ),
    path(
        f"{S}stock-counts/<uuid:count_id>/items/",
        views.StockCountItemsView.as_view(),
        name="stock-count-items",
    ),
    path(
        f"{S}stock-counts/<uuid:count_id>/submit/",
        views.StockCountSubmitView.as_view(),
        name="stock-count-submit",
    ),
    path(
        f"{S}stock-counts/<uuid:count_id>/approve/",
        views.StockCountApproveView.as_view(),
        name="stock-count-approve",
    ),
    path(
        f"{S}stock-counts/<uuid:count_id>/cancel/",
        views.StockCountCancelView.as_view(),
        name="stock-count-cancel",
    ),
    path(f"{S}alerts/", views.AlertListView.as_view(), name="alerts"),
    path(f"{S}reports/summary/", views.SummaryReportView.as_view(), name="reports-summary"),
]
