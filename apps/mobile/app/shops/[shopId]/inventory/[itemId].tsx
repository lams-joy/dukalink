import { useState } from "react";
import { Text } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../../src/ui";
import { api } from "../../../../src/api";
import { sendOp } from "../../../../src/offline";

export default function ItemDetail() {
  const { shopId, itemId } = useLocalSearchParams<{ shopId: string; itemId: string }>();
  const { data: item, error, loading, reload } = useLoad<any>(`/shops/${shopId}/inventory/${itemId}/`);
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const [level, setLevel] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const adj = useAction();
  const set = useAction();

  const adjust = () => adj.run(async () => {
    const r = await sendOp(shopId!, "stock_adjustment", { shop_product_id: itemId, quantity_base_delta: delta, reason });
    setNote(r.queued ? "Saved on this phone - it will sync when you are online." : "Correction saved.");
    setDelta(""); setReason(""); reload();
  });
  const saveLevel = () => set.run(async () => {
    await api(`/shops/${shopId}/inventory/${itemId}/settings/`, { method: "PATCH", body: { reorder_level_base: level } });
    reload();
  });

  return (
    <Screen title={item?.product_name ?? "Item"}>
      <Loading loading={loading} error={error} />
      {item ? <>
        <Text>In stock: {item.quantity_base} {item.base_unit}</Text>
        <Text>Reorder level: {item.reorder_level_base ?? "not set"} | Tracking: {item.tracking_mode}</Text>
        <Gap /><Text>Correct stock (use a negative number to remove)</Text>
        <Field label={`Change in ${item.base_unit}`} value={delta} onChangeText={setDelta} keyboardType="numeric" />
        <Field label="Reason" value={reason} onChangeText={setReason} />
        <ErrorText error={adj.error} />{note ? <Text>{note}</Text> : null}
        <Btn title="Save correction" disabled={adj.busy} onPress={adjust} />
        <Gap /><Field label={`Reorder level (${item.base_unit})`} value={level} onChangeText={setLevel} keyboardType="numeric" />
        <ErrorText error={set.error} />
        <Btn title="Save reorder level" disabled={set.busy} onPress={saveLevel} />
      </> : null}
    </Screen>
  );
}
