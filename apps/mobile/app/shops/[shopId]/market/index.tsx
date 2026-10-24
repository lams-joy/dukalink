import { useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Nav, Field, Loading, useLoad } from "../../../../src/ui";

export default function Market() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading } = useLoad<any[]>("/marketplace/offers/", true);
  const [q, setQ] = useState("");
  const rows = (data ?? []).filter((o) => JSON.stringify(o.product).toLowerCase().includes(q.toLowerCase()));
  return (
    <Screen title="Marketplace">
      <Field label="Filter" value={q} onChangeText={setQ} />
      <Loading loading={loading} error={error} />
      {rows.map((o) => (
        <View key={o.id}>
          <Nav href={`/shops/${shopId}/market/${o.id}`}>
            {o.product?.name ?? "Product"} - {o.currency} {o.price_per_unit} per {o.unit?.unit_name ?? "unit"} - {o.wholesaler.business_name}
          </Nav>
        </View>
      ))}
      {!loading && rows.length === 0 ? <Text>No offers yet.</Text> : null}
    </Screen>
  );
}
