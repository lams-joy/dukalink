import { useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Text, Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../src/ui";
import { sendOp } from "../../../src/offline";
import { unitsFor, Unit } from "../../../src/units";

export default function Sell() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
    const inv = useLoad<any[]>(`/shops/${shopId}/inventory/`, true);
  const [item, setItem] = useState<any>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [unitId, setUnitId] = useState("");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const pick = useAction();
  const save = useAction();

  const choose = (i: any) => pick.run(async () => {
    const u = (await unitsFor(shopId!, i)).filter((x) => x.is_sale_unit);
    setItem(i); setUnits(u); setUnitId(u[0]?.id ?? "");
  });
  const sell = () => save.run(async () => {
    const r = await sendOp(shopId!, "sale", { items: [{ shop_product_id: item.id, product_unit_id: unitId, quantity: qty, unit_price: price }] });
    setSaved(r.queued ? "Saved on this phone - it will sync when you are online." : "Sale recorded.");
    setItem(null); setQty(""); setPrice("");
  });

  return (
    <Screen title="Record a sale">
      {saved ? <Text>{saved}</Text> : null}
      <Loading loading={inv.loading} error={inv.error} />
      {!item ? inv.data?.map((i) => <View key={i.id}><Btn title={`${i.product_name} (${i.quantity_base} ${i.base_unit})`} onPress={() => choose(i)} /></View>) : (
        <>
          <Text>Selling: {item.product_name} - {item.quantity_base} {item.base_unit} in stock</Text>
          {units.map((u) => <Btn key={u.id} title={`${u.id === unitId ? "[x] " : ""}${u.unit_name}`} onPress={() => setUnitId(u.id)} />)}
          <Field label="Quantity" value={qty} onChangeText={setQty} keyboardType="numeric" />
          <Field label="Price per unit (KES)" value={price} onChangeText={setPrice} keyboardType="numeric" />
          <ErrorText error={save.error} /><Gap />
          <Btn title="Record sale" disabled={save.busy || !unitId} onPress={sell} />
          <Btn title="Pick another product" onPress={() => setItem(null)} />
        </>
      )}
      <ErrorText error={pick.error} />
    </Screen>
  );
}
