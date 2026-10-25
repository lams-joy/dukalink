import { useEffect, useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Text, Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";
import { unitsFor, Unit } from "../../../../src/units";

function Row({ shopId, countId, item, productId, editable, onSaved }: any) {
  const [units, setUnits] = useState<Unit[]>([]);
  const [unitId, setUnitId] = useState("");
  const [qty, setQty] = useState(item.counted_quantity_base != null ? String(item.counted_quantity_base) : "");
  const act = useAction();
  useEffect(() => {
    if (!editable) return;
    unitsFor(shopId, { product_id: productId, product_name: item.product_name }).then((u) => {
      setUnits(u); setUnitId((u.find((x) => Number(x.base_quantity) === 1) ?? u[0])?.id ?? "");
    }).catch(() => {});
  }, [editable]);
  const save = () => act.run(async () => {
    await api(`/shops/${shopId}/stock-counts/${countId}/items/`, { method: "PUT", body: { idempotency_key: uuid(), items: [{ shop_product_id: item.shop_product_id, product_unit_id: unitId, quantity: qty }] } });
    onSaved();
  });
  return (
    <View>
      <Text>{item.product_name}: expected {item.expected_quantity_base} {item.base_unit}{item.counted_quantity_base != null ? ` | counted ${item.counted_quantity_base} | difference ${item.variance_base}` : ""}</Text>
      {editable ? <>
        {units.map((u) => <Btn key={u.id} title={`${u.id === unitId ? "[x] " : ""}${u.unit_name}`} onPress={() => setUnitId(u.id)} />)}
        <Field label="Counted quantity" value={qty} onChangeText={setQty} keyboardType="numeric" />
        <Btn title="Save count" disabled={act.busy || !unitId || qty === ""} onPress={save} /><ErrorText error={act.error} />
      </> : null}
    </View>
  );
}

export default function Count() {
  const { shopId, countId } = useLocalSearchParams<{ shopId: string; countId: string }>();
  const { data: c, error, loading, reload } = useLoad<any>(`/shops/${shopId}/stock-counts/${countId}/`);
  const inv = useLoad<any[]>(`/shops/${shopId}/inventory/`, true);
  const pid = new Map((inv.data ?? []).map((i) => [i.id, i.product_id]));
  const [reason, setReason] = useState("");
  const act = useAction();
  const post = (verb: string, body: object) => act.run(async () => { await api(`/shops/${shopId}/stock-counts/${countId}/${verb}/`, { method: "POST", body }); reload(); });
  return (
    <Screen title="Stock count">
      <Loading loading={loading} error={error} />
      {c ? <>
        <Text>Status: {c.status} | {c.counted_items}/{c.total_items} counted{c.resolution_note ? ` | ${c.resolution_note}` : ""}</Text>
        <Gap />
        {inv.data && c.items.map((i: any) => <Row key={i.id + String(i.counted_quantity_base)} productId={pid.get(i.shop_product_id)} shopId={shopId} countId={countId} item={i} editable={c.status === "in_progress"} onSaved={reload} />)}
        <Gap /><ErrorText error={act.error} />
        {c.status === "in_progress" ? <Btn title="Submit count for approval" disabled={act.busy} onPress={() => post("submit", { idempotency_key: uuid() })} /> : null}
        {c.status === "submitted" ? <Btn title="Approve (manager) - applies the differences to stock" disabled={act.busy} onPress={() => post("approve", { idempotency_key: uuid() })} /> : null}
        {["in_progress", "submitted"].includes(c.status) ? <>
          <Field label="Reason for cancelling" value={reason} onChangeText={setReason} />
          <Btn title="Cancel count (manager)" disabled={act.busy || !reason} onPress={() => post("cancel", { idempotency_key: uuid(), reason })} />
        </> : null}
      </> : null}
    </Screen>
  );
}
