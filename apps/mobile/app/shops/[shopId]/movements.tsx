import { useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Field, Btn, ErrorText, Loading, useLoad, useAction } from "../../../src/ui";
import { api, uuid } from "../../../src/api";

export default function Movements() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading, reload } = useLoad<any[]>(`/shops/${shopId}/stock-movements/`, true);
  const inv = useLoad<any[]>(`/shops/${shopId}/inventory/`, true);
  const names = new Map((inv.data ?? []).map((i) => [i.id, i.product_name]));
  const [reason, setReason] = useState("");
  const act = useAction();
  const reverse = (id: string) => act.run(async () => { await api(`/shops/${shopId}/stock-movements/${id}/reverse/`, { method: "POST", body: { idempotency_key: uuid(), reason } }); reload(); });
  return (
    <Screen title="Stock movements">
      <Field label="Reason (needed to reverse a mistake - manager only)" value={reason} onChangeText={setReason} />
      <Loading loading={loading} error={error} /><ErrorText error={act.error} />
      {data?.map((m) => (
        <View key={m.id}>
          <Text>{new Date(m.created_at).toLocaleString()} - {names.get(m.shop_product_id) ?? ""} {m.movement_type}: {m.quantity_base_delta} (balance {m.balance_after_base}){m.note ? ` - ${m.note}` : ""}</Text>
          {reason && m.movement_type !== "reversal" ? <Btn title="Reverse this" disabled={act.busy} onPress={() => reverse(m.id)} /> : null}
        </View>
      ))}
    </Screen>
  );
}
