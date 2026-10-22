from django.urls import path

from . import views

urlpatterns = [
    path("catalog/products/", views.ProductListView.as_view(), name="catalog-products"),
]
