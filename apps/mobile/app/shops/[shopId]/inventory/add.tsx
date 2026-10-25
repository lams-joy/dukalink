import { useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Text, Screen, Field, Btn, ErrorText, Gap, useAction } from "../../../../src/ui";
import { api, apiList, uuid } from "../../../../src/api";

export default function AddProduct() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [picked, setPicked] = useState<any>(null);
  const [unitId, setUnitId] = useState("");
  const [qty, setQty] = useState("");
  const search = useAction();
  const save = useAction();

  const find = () => search.run(async () => setResults(await apiList(`/catalog/products/?q=${encodeURIComponent(q)}`)));
  const track = () => save.run(async () => {
    const item = await api(`/shops/${shopId}/inventory/`, { method: "POST", body: { product_id: picked.id } });
    if (qty && unitId) {
      await api(`/shops/${shopId}/inventory/${item.id}/opening-stock/`, {
        method: "POST", body: { idempotency_key: uuid(), product_unit_id: unitId, quantity: qty },
      });
    }
    router.replace(`/shops/${shopId}/inventory`);
  });

  return (
    <Screen title="Track a product">
      <Field label="Search the catalogue" value={q} onChangeText={setQ} />
      <Btn title="Search" onPress={find} /><ErrorText error={search.error} />
      {!picked && results.map((p) => (
        <View key={p.id}><Btn title={`${p.name}${p.brand ? " - " + p.brand : ""}`} onPress={() => { setPicked(p); setUnitId(p.units[0]?.id ?? ""); }} /></View>
      ))}
      {picked ? <>
        <Gap /><Text>Selected: {picked.name} (base unit {picked.base_unit})</Text>
        <Text>Opening stock (optional) - pick a unit:</Text>
        {picked.units.map((u: any) => (
          <Btn key={u.id} title={`${u.id === unitId ? "[x] " : ""}${u.unit_name} (= ${u.base_quantity} ${picked.base_unit})`} onPress={() => setUnitId(u.id)} />
        ))}
        <Field label="Quantity in that unit" value={qty} onChangeText={setQty} keyboardType="numeric" />
        <ErrorText error={save.error} />
        <Btn title="Start tracking" disabled={save.busy} onPress={track} />
      </> : null}
    </Screen>
  );
}
