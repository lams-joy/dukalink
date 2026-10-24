import { Text, View } from "react-native";
import { Screen, Loading, useLoad } from "../../../../src/ui";

export default function Wholesalers() {
  const { data, error, loading } = useLoad<any[]>("/marketplace/wholesalers/", true);
  return (
    <Screen title="Verified wholesalers">
      <Loading loading={loading} error={error} />
      {data?.map((w) => (
        <View key={w.id}><Text>{w.business_name} - {w.location_text} - {w.contact_phone} - {w.offer_count} offers</Text></View>
      ))}
      {!loading && data?.length === 0 ? <Text>None yet.</Text> : null}
    </Screen>
  );
}
