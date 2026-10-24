import { apiList } from "./api";

export type Unit = { id: string; unit_name: string; base_quantity: string; is_sale_unit: boolean; is_purchase_unit: boolean };

/** Units for a tracked product: look in the shared catalogue first, then the shop's own products. */
export async function unitsFor(shopId: string, item: { product_id: string; product_name: string }): Promise<Unit[]> {
  const shared = await apiList(`/catalog/products/?q=${encodeURIComponent(item.product_name)}`);
  let p = shared.find((x: any) => x.id === item.product_id);
  if (!p) p = (await apiList(`/shops/${shopId}/products/`)).find((x: any) => x.id === item.product_id);
  return p?.units ?? [];
}
