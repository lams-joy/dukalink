from django.db.models import Q
from rest_framework.generics import ListAPIView

from .models import Product
from .serializers import ProductSerializer


class ProductListView(ListAPIView):
    """Search the shared catalogue: ?q=<text> matches name, brand or barcode."""

    serializer_class = ProductSerializer

    def get_queryset(self):
        # Shared entries only: another shop's custom products must never appear here.
        qs = Product.objects.filter(is_active=True, owner_shop__isnull=True).prefetch_related("units").order_by("name")
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(barcode=q))
        return qs
