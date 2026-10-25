import { useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Text, Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../src/ui";
import { sendOp } from "../../../src/offline";
import { unitsFor, Unit } from "../../../src/units";

export default function Receive() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
    const inv = useLoad<any[]>(`/shops/${shopId}/inventory/`, true);
  const [item, setItem] = useState<any>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [unitId, setUnitId] = useState("");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [supplier, setSupplier] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const pick = useAction();
  const save = useAction();

  const choose = (i: any) => pick.run(async () => {
    const u = (await unitsFor(shopId!, i)).filter((x) => x.is_purchase_unit);
    setItem(i); setUnits(u); setUnitId(u[0]?.id ?? "");
  });
  const submit = () => save.run(async () => {
    const r = await sendOp(shopId!, "purchase_receipt", { supplier_name: supplier,
      items: [{ product_id: item.product_id, product_unit_id: unitId, quantity: qty, ...(cost ? { unit_cost: cost } : {}) }] });
    setSaved(r.queued ? "Saved on this phone - it will sync when you are online." : "Receipt saved.");
    setItem(null); setQty(""); setCost("");
  });

  return (
    <Screen title="Goods received">
      {saved ? <Text>{saved}</Text> : null}
      <Loading loading={inv.loading} error={inv.error} />
      {!item ? inv.data?.map((i) => <View key={i.id}><Btn title={i.product_name} onPress={() => choose(i)} /></View>) : (
        <>
          <Text>Receiving: {item.product_name}</Text>
          {units.map((u) => <Btn key={u.id} title={`${u.id === unitId ? "[x] " : ""}${u.unit_name} (= ${u.base_quantity} ${item.base_unit})`} onPress={() => setUnitId(u.id)} />)}
          <Field label="Quantity received" value={qty} onChangeText={setQty} keyboardType="numeric" />
          <Field label="Cost per unit (KES, optional)" value={cost} onChangeText={setCost} keyboardType="numeric" />
          <Field label="Supplier (optional)" value={supplier} onChangeText={setSupplier} autoCapitalize="words" />
          <ErrorText error={save.error} /><Gap />
          <Btn title="Save receipt" disabled={save.busy || !unitId} onPress={submit} />
          <Btn title="Pick another product" onPress={() => setItem(null)} />
        </>
      )}
      <ErrorText error={pick.error} />
    </Screen>
  );
}
