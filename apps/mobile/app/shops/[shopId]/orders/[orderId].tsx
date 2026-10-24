import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";

export default function OrderDetail() {
  const { shopId, orderId } = useLocalSearchParams<{ shopId: string; orderId: string }>();
  const { data: o, error, loading, reload } = useLoad<any>(`/shops/${shopId}/orders/${orderId}/`);
  const [got, setGot] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [key] = useState(uuid());
  const act = useAction();
  useEffect(() => { if (o) setGot(Object.fromEntries(o.items.map((i: any) => [i.id, String(i.received_quantity ?? i.quantity)]))); }, [o]);

  const receive = () => act.run(async () => {
    await api(`/shops/${shopId}/orders/${orderId}/receive/`, { method: "POST", body: {
      idempotency_key: key, receipt_note: note,
      items: o.items.map((i: any) => ({ item_id: i.id, received_quantity: got[i.id] })) } });
    reload();
  });
  const cancel = () => act.run(async () => { await api(`/shops/${shopId}/orders/${orderId}/cancel/`, { method: "POST", body: { reason } }); reload(); });

  return (
    <Screen title="Order">
      <Loading loading={loading} error={error} />
      {o ? <>
        <Text>{o.wholesaler?.business_name} ({o.wholesaler?.contact_phone}) - {o.status}</Text>
        <Text>{o.delivery_method}{o.delivery_address ? `: ${o.delivery_address}` : ""}{o.group_order_id ? " | from a group buy" : ""}</Text>
        {o.status_note ? <Text>Note from wholesaler: {o.status_note}</Text> : null}
        {o.items.map((i: any) => (
          <View key={i.id}>
            <Text>{i.quantity} x {i.product_name} ({i.unit_name}) at {i.unit_price} = {i.line_total}</Text>
            {o.status === "dispatched" ? <Field label="Quantity you actually received" value={got[i.id] ?? ""} onChangeText={(v) => setGot({ ...got, [i.id]: v })} keyboardType="numeric" /> : null}
            {i.received_quantity != null ? <Text>  Received {i.received_quantity}{i.shortage ? `, short by ${i.shortage}` : ""}</Text> : null}
          </View>
        ))}
        <Text>Delivery fee {o.delivery_fee} | Total {o.currency} {o.total_amount}</Text>
        {o.purchase_receipt_id ? <Text>Stock was added automatically from this delivery.</Text> : null}
        <Gap />
        {o.status === "dispatched" ? <>
          <Field label="Delivery note (optional)" value={note} onChangeText={setNote} />
          <Btn title="Confirm delivery received" disabled={act.busy} onPress={receive} />
        </> : null}
        {["submitted", "confirmed"].includes(o.status) && !o.group_order_id ? <>
          <Field label="Reason for cancelling" value={reason} onChangeText={setReason} />
          <Btn title="Cancel order" disabled={act.busy || !reason} onPress={cancel} />
        </> : null}
        <ErrorText error={act.error} />
      </> : null}
    </Screen>
  );
}
