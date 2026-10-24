import { useState } from "react";
import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Nav, Btn, Gap, Loading, useLoad } from "../../../../src/ui";

export default function Groups() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const [mine, setMine] = useState(false);
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/group-orders/${mine ? "?mine=true" : ""}`, true);
  return (
    <Screen title="Group buying">
      <Btn title={mine ? "Showing: my groups (tap for open groups)" : "Showing: open groups (tap for my groups)"} onPress={() => setMine(!mine)} />
      <Nav href={`/shops/${shopId}/groups/new`}>+ Start a group buy</Nav>
      <Gap /><Loading loading={loading} error={error} />
      {data?.map((g) => (
        <View key={g.id}>
          <Nav href={`/shops/${shopId}/groups/${g.id}`}>
            {g.product_name} ({g.unit_name}) - {Math.round(parseFloat(g.progress) * 100)}% - {g.status} - ends {new Date(g.deadline).toLocaleDateString()}
          </Nav>
        </View>
      ))}
      {!loading && data?.length === 0 ? <Text>No groups here.</Text> : null}
    </Screen>
  );
}
