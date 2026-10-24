import { Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Nav, Loading, useLoad } from "../../../../src/ui";

export default function Orders() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/orders/`, true);
  return (
    <Screen title="My orders">
      <Loading loading={loading} error={error} />
      {data?.map((o) => (
        <View key={o.id}>
          <Nav href={`/shops/${shopId}/orders/${o.id}`}>
            {o.wholesaler?.business_name} - {o.status}{o.has_shortage ? " (short delivery)" : ""} - KES {o.total_amount} - {new Date(o.submitted_at).toLocaleDateString()}
          </Nav>
        </View>
      ))}
      {!loading && data?.length === 0 ? <Text>No orders yet.</Text> : null}
    </Screen>
  );
}
