from django.urls import path

from . import views

W = "wholesalers/<uuid:wholesaler_id>/"

urlpatterns = [
    # a wholesaler's own workspace
    path("wholesalers/", views.WholesalerListCreateView.as_view(), name="wholesaler-list"),
    path(W, views.WholesalerDetailView.as_view(), name="wholesaler-detail"),
    path(f"{W}members/", views.WholesalerMemberCreateView.as_view(), name="wholesaler-members"),
    path(f"{W}audit-events/", views.WholesalerAuditView.as_view(), name="wholesaler-audit"),
    path(f"{W}offers/", views.OfferListCreateView.as_view(), name="wholesaler-offers"),
    path(f"{W}offers/<uuid:offer_id>/", views.OfferDetailView.as_view(), name="wholesaler-offer"),
    path(
        f"{W}offers/<uuid:offer_id>/tiers/",
        views.OfferTiersView.as_view(),
        name="wholesaler-offer-tiers",
    ),
    # marketplace: what shops see
    path("marketplace/offers/", views.MarketplaceOfferListView.as_view(), name="market-offers"),
    path(
        "marketplace/offers/<uuid:offer_id>/",
        views.MarketplaceOfferDetailView.as_view(),
        name="market-offer",
    ),
    path(
        "marketplace/offers/<uuid:offer_id>/quote/",
        views.MarketplaceQuoteView.as_view(),
        name="market-offer-quote",
    ),
    path(
        "marketplace/wholesalers/",
        views.MarketplaceWholesalerListView.as_view(),
        name="market-wholesalers",
    ),
    path(
        "marketplace/wholesalers/<uuid:wholesaler_id>/",
        views.MarketplaceWholesalerDetailView.as_view(),
        name="market-wholesaler",
    ),
    # platform administration
    path("admin/suppliers/pending/", views.PendingSuppliersView.as_view(), name="admin-pending"),
    path(
        "admin/suppliers/<uuid:wholesaler_id>/verify/",
        views.VerifySupplierView.as_view(),
        name="admin-verify",
    ),
    path(
        "admin/suppliers/<uuid:wholesaler_id>/suspend/",
        views.SuspendSupplierView.as_view(),
        name="admin-suspend",
    ),
]
