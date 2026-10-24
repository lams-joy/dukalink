import { useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Screen, Nav, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";

export default function Counts() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const router = useRouter();
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/stock-counts/`, true);
  const [note, setNote] = useState("");
  const act = useAction();
  const start = () => act.run(async () => {
    const c = await api(`/shops/${shopId}/stock-counts/`, { method: "POST", body: { idempotency_key: uuid(), note } });
    router.push(`/shops/${shopId}/counts/${c.id}`);
  });
  return (
    <Screen title="Stock counts">
      <Text>Count what is really on the shelves. Differences become stock corrections once a manager approves.</Text>
      <Field label="Note (optional)" value={note} onChangeText={setNote} />
      <Btn title="Start a new count (all tracked products)" disabled={act.busy} onPress={start} /><ErrorText error={act.error} />
      <Gap /><Loading loading={loading} error={error} />
      {data?.map((c) => (
        <View key={c.id}><Nav href={`/shops/${shopId}/counts/${c.id}`}>{new Date(c.started_at).toLocaleDateString()} - {c.status} - {c.counted_items}/{c.total_items} counted{c.note ? ` - ${c.note}` : ""}</Nav></View>
      ))}
    </Screen>
  );
}
