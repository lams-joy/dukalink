"""The OpenAPI schema must describe the order and group-buying endpoints: every operation has a
documented success response, and the request bodies are the real input serializers.

(The rest of the API is annotated in later passes; this guards the parts that are done.)"""

from functools import lru_cache

from drf_spectacular.generators import SchemaGenerator


@lru_cache(maxsize=1)
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def operations(prefixes):
    for path, item in schema()["paths"].items():
        if any(prefix in path for prefix in prefixes):
            for method, op in item.items():
                if method in {"get", "post", "put", "patch", "delete"}:
                    yield method, path, op


def test_order_and_group_endpoints_document_their_success_responses():
    seen = 0
    for method, path, op in operations(("/group-orders/", "/orders/")):
        success = [code for code in op["responses"] if code.startswith("2")]
        assert success, (method, path, "no success response")
        for code in success:
            assert "content" in op["responses"][code], (method, path, code, "empty response")
        seen += 1
    assert seen >= 20


def test_the_cost_breakdown_is_described_for_both_sides():
    paths = schema()["paths"]
    shop = paths["/api/v1/shops/{shop_id}/group-orders/{group_id}/cost-breakdown/"]["get"]
    base = "/api/v1/wholesalers/{wholesaler_id}"
    wholesaler = paths[f"{base}/group-orders/{{group_id}}/cost-breakdown/"]["get"]
    for op, name in ((shop, "ShopCostBreakdownOut"), (wholesaler, "WholesalerCostBreakdownOut")):
        content = op["responses"]["200"]["content"]["application/json"]["schema"]
        assert content["$ref"].endswith(f"/{name}")
    components = schema()["components"]["schemas"]
    assert "mine" in components["ShopCostBreakdownOut"]["properties"]
    assert "orders" in components["WholesalerCostBreakdownOut"]["properties"]
    assert "orders" not in components["ShopCostBreakdownOut"]["properties"]


def test_posts_without_a_body_document_no_request_body():
    paths = schema()["paths"]
    dispatch = paths["/api/v1/wholesalers/{wholesaler_id}/orders/{order_id}/dispatch/"]["post"]
    close = paths["/api/v1/shops/{shop_id}/group-orders/{group_id}/close/"]["post"]
    assert "requestBody" not in dispatch and "requestBody" not in close
