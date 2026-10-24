import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Btn, ErrorText, Loading, useLoad, useAction } from "../../../src/ui";
import { api, uuid } from "../../../src/api";

export default function Orders() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading, reload } = useLoad<any[]>(`/shops/${shopId}/orders/`, true);
  const act = useAction();
  const cancel = (id: string) => act.run(async () => { await api(`/shops/${shopId}/orders/${id}/cancel/`, { method: "POST", body: { reason: "Cancelled by shop" } }); reload(); });
  const receive = (o: any) => act.run(async () => {
    // Simplest case: everything arrived as ordered.
    await api(`/shops/${shopId}/orders/${o.id}/receive/`, {
      method: "POST",
      body: { idempotency_key: uuid(), items: o.items.map((i: any) => ({ item_id: i.id, received_quantity: i.quantity })) },
    });
    reload();
  });
  return (
    <Screen title="My orders">
      <Loading loading={loading} error={error} /><ErrorText error={act.error} />
      {data?.map((o) => (
        <View key={o.id} style={{ marginBottom: 12 }}>
          <Text>{o.wholesaler?.business_name} - {o.status} - KES {o.total_amount}</Text>
          {o.items?.map((i: any) => <Text key={i.id}>  {i.quantity} x {i.product_name} ({i.unit_name})</Text>)}
          {["submitted", "confirmed"].includes(o.status) && !o.group_order_id ? <Btn title="Cancel order" onPress={() => cancel(o.id)} /> : null}
          {o.status === "dispatched" ? <Btn title="Received in full" onPress={() => receive(o)} /> : null}
        </View>
      ))}
      {!loading && data?.length === 0 ? <Text>No orders yet.</Text> : null}
    </Screen>
  );
}
