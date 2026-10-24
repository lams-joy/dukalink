import { useCallback, useEffect, useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Btn, ErrorText, Gap, useAction } from "../../../src/ui";
import { QueuedOp, discard, flush, queueFor } from "../../../src/offline";

export default function Queue() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const [ops, setOps] = useState<QueuedOp[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const act = useAction();
  const refresh = useCallback(async () => setOps(await queueFor(shopId!)), [shopId]);
  useEffect(() => { refresh(); }, [refresh]);
  const sync = () => act.run(async () => {
    const r = await flush(shopId!);
    setMsg(r.offline ? "Still offline." : `Synced ${r.sent}, needs attention ${r.failed}.`);
    refresh();
  });
  return (
    <Screen title="Waiting to sync">
      <Text>Records made without internet are kept on this phone until they can be sent.</Text>
      <Gap /><Btn title="Sync now" disabled={act.busy} onPress={sync} />
      {msg ? <Text>{msg}</Text> : null}<ErrorText error={act.error} />
      {ops.length === 0 ? <Text>Nothing waiting.</Text> : null}
      {ops.map((o) => (
        <View key={o.operation_id}>
          <Text>{new Date(o.created_at).toLocaleString()} - {o.operation_type} - {o.state}</Text>
          <Text>{JSON.stringify(o.payload)}</Text>
          {o.error ? <Text>Problem: {o.error}</Text> : null}
          {o.state === "failed" ? <Btn title="Discard" onPress={async () => { await discard(o.operation_id); refresh(); }} /> : null}
        </View>
      ))}
    </Screen>
  );
}
