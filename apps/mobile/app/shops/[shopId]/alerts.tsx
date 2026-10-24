import { Text } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Loading, useLoad } from "../../../src/ui";

export default function Alerts() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data, error, loading } = useLoad<any[]>(`/shops/${shopId}/alerts/`, true);
  return (
    <Screen title="Low-stock alerts">
      <Loading loading={loading} error={error} />
      {data?.length === 0 ? <Text>All good - nothing is low.</Text> : null}
      {data?.map((a) => <Text key={a.shop_product_id}>{a.product_name}: {a.quantity_base} left (reorder at {a.reorder_level_base}, short by {a.shortfall_base} {a.base_unit})</Text>)}
    </Screen>
  );
}
