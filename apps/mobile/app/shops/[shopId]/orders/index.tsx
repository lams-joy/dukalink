import { Pressable } from "react-native";
import { Link, useLocalSearchParams } from "expo-router";
import { Screen, Text, View, Card, Pill, statusTone, kes, Loading, useLoad } from "../../../../src/ui";
import { theme as t } from "../../../../src/theme";

export default function Orders() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/orders/`, true);
  return (
    <Screen title="My orders">
      <Loading loading={loading} error={error} />
      {data?.map((o) => (
        <Link key={o.id} href={`/shops/${shopId}/orders/${o.id}`} asChild>
          <Pressable>
            <Card>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={{ fontWeight: "700", fontSize: 16 }}>{o.wholesaler?.business_name}</Text>
                <Text style={{ fontWeight: "800", color: t.color.primary }}>{kes(o.total_amount)}</Text>
              </View>
              <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
                <Pill tone={statusTone(o.status)}>{o.status}</Pill>
                {o.group_order_id ? <Pill tone="info">Group buy</Pill> : null}
                {o.has_shortage ? <Pill tone="warn">Short delivery</Pill> : null}
              </View>
              <Text style={{ color: t.color.muted, marginBottom: 0 }}>{o.items?.length ?? 0} item(s) - {new Date(o.submitted_at).toLocaleDateString()}</Text>
            </Card>
          </Pressable>
        </Link>
      ))}
      {!loading && data?.length === 0 ? <Text>No orders yet. Find something in the Marketplace.</Text> : null}
    </Screen>
  );
}
