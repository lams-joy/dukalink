import { useState } from "react";
import { Pressable } from "react-native";
import { Link, useLocalSearchParams } from "expo-router";
import { Screen, Text, View, Card, Grid, Pill, ProgressBar, statusTone, Nav, Btn, Loading, useLoad } from "../../../../src/ui";
import { theme as t } from "../../../../src/theme";

export default function Groups() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const [mine, setMine] = useState(false);
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/group-orders/${mine ? "?mine=true" : ""}`, true);
  return (
    <Screen title="Group buying">
      <Text style={{ color: t.color.muted }}>Join other shops to buy in bulk and unlock lower prices.</Text>
      <Nav icon="plus-circle" href={`/shops/${shopId}/groups/new`}>Start a group buy</Nav>
      <View style={{ flexDirection: "row" }}>
        <View style={{ flex: 1, marginRight: 6 }}><Btn kind={mine ? "plain" : "primary"} title="Open groups" onPress={() => setMine(false)} /></View>
        <View style={{ flex: 1 }}><Btn kind={mine ? "primary" : "plain"} title="My groups" onPress={() => setMine(true)} /></View>
      </View>
      <Loading loading={loading} error={error} />
      <Grid min={300}>
        {(data ?? []).map((g) => (
          <Link key={g.id} href={`/shops/${shopId}/groups/${g.id}`} asChild>
            <Pressable><Card style={{ marginBottom: 0 }}>
              <Text style={{ fontWeight: "700", fontSize: 16, marginBottom: 2 }}>{g.product_name}</Text>
              <Text style={{ color: t.color.muted }}>per {g.unit_name} - ends {new Date(g.deadline).toLocaleDateString()}</Text>
              <ProgressBar value={parseFloat(g.progress) || 0} />
              <Text style={{ marginBottom: 6 }}>{Math.round((parseFloat(g.progress) || 0) * 100)}% of target - {g.committed_quantity}/{g.target_quantity}</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
                <Pill tone={statusTone(g.status)}>{g.status}</Pill>
                <Pill>{g.participant_count} shops</Pill>
              </View>
            </Card></Pressable>
          </Link>
        ))}
      </Grid>
      {!loading && data?.length === 0 ? <Text>No groups here yet.</Text> : null}
    </Screen>
  );
}
