import { useState } from "react";
import { useLocalSearchParams } from "expo-router";
import { Screen, Text, Field, Grid, ProductCard, Pill, Nav, Loading, useLoad } from "../../../../src/ui";

export default function Market() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading } = useLoad<any[]>("/marketplace/offers/", true);
  const [q, setQ] = useState("");
  const rows = (data ?? []).filter((o) => `${o.product?.name} ${o.wholesaler?.business_name}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <Screen title="Marketplace">
      <Field label="Search products or wholesalers" value={q} onChangeText={setQ} placeholder="e.g. sugar" />
      <Nav icon="users" href={`/shops/${shopId}/groups`}>Group buying: pool orders for lower prices</Nav>
      <Loading loading={loading} error={error} />
      <Grid min={220}>
        {rows.map((o) => (
          <ProductCard key={o.id} href={`/shops/${shopId}/market/${o.id}`} name={o.product?.name ?? "Product"}
            subtitle={`${o.wholesaler.business_name} - ${o.wholesaler.location_text}`}
            price={`${o.currency} ${Number(o.price_per_unit).toLocaleString()}`} priceNote={`per ${o.unit?.unit_name}`}
            pills={<>
              <Pill tone={o.availability === "in_stock" ? "good" : o.availability === "limited" ? "warn" : "bad"}>{String(o.availability).replace("_", " ")}</Pill>
              <Pill>Min {o.minimum_order_quantity}</Pill>
              {o.tiers?.length ? <Pill tone="info">Bulk discount</Pill> : null}
            </>} />
        ))}
      </Grid>
      {!loading && rows.length === 0 ? <Text>No offers match.</Text> : null}
    </Screen>
  );
}
