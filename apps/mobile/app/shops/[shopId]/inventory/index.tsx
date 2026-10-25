import { useState } from "react";
import { useLocalSearchParams } from "expo-router";
import { Screen, Text, Field, Grid, ProductCard, Pill, Nav, Loading, useLoad } from "../../../../src/ui";

export default function Inventory() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/inventory/`, true);
  const [q, setQ] = useState("");
  const rows = (data ?? []).filter((i) => i.product_name.toLowerCase().includes(q.toLowerCase()));
  return (
    <Screen title="Inventory">
      <Field label="Search your stock" value={q} onChangeText={setQ} placeholder="e.g. maize flour" />
      <Loading loading={loading} error={error} />
      <Grid min={200}>
        {rows.map((i) => (
          <ProductCard key={i.id} href={`/shops/${shopId}/inventory/${i.id}`} name={i.product_name}
            subtitle={i.reorder_level_base ? `Reorder at ${i.reorder_level_base} ${i.base_unit}` : "No reorder level set"}
            price={`${i.quantity_base} ${i.base_unit}`} priceNote="in stock"
            pills={Number(i.quantity_base) <= 0 ? <Pill tone="bad">Out of stock</Pill> : i.is_low_stock ? <Pill tone="warn">Low stock</Pill> : <Pill tone="good">In stock</Pill>} />
        ))}
      </Grid>
      {!loading && rows.length === 0 ? <Text>Nothing tracked yet.</Text> : null}
      <Nav icon="plus-circle" href={`/shops/${shopId}/inventory/add`}>Track a catalogue product</Nav>
      <Nav icon="edit-3" href={`/shops/${shopId}/inventory/new-product`}>Add my own product</Nav>
    </Screen>
  );
}
