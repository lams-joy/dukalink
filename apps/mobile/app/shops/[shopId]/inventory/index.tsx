import { useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Nav, Field, Loading, useLoad } from "../../../../src/ui";

export default function Inventory() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/inventory/`, true);
  const [q, setQ] = useState("");
  const rows = (data ?? []).filter((i) => i.product_name.toLowerCase().includes(q.toLowerCase()));
  return (
    <Screen title="Inventory">
      <Field label="Search" value={q} onChangeText={setQ} />
      <Loading loading={loading} error={error} />
      {rows.map((i) => (
        <View key={i.id}>
          <Nav href={`/shops/${shopId}/inventory/${i.id}`}>
            {i.product_name}: {i.quantity_base} {i.base_unit}{i.is_low_stock ? "  (LOW)" : ""}
          </Nav>
        </View>
      ))}
      {!loading && rows.length === 0 ? <Text>Nothing tracked yet.</Text> : null}
      <Nav href={`/shops/${shopId}/inventory/add`}>+ Track a product</Nav>
    </Screen>
  );
}
