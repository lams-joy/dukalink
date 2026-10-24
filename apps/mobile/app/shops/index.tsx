import { Text, View } from "react-native";
import { Screen, Nav, Gap, Btn, Loading, useLoad } from "../../src/ui";
import { useAuth } from "../../src/auth";

export default function Shops() {
  const { user, signOut } = useAuth();
  const { data, error, loading, reload } = useLoad<any[]>("/shops/", true);
  return (
    <Screen title="Your shops">
      <Text>Signed in as {user?.full_name} ({user?.phone_number})</Text>
      <Gap /><Loading loading={loading} error={error} />
      {data?.length === 0 ? <Text>No shops yet.</Text> : null}
      {data?.map((s) => (
        <View key={s.id}><Nav href={`/shops/${s.id}`}>{s.name} - {s.location_text} ({s.my_role})</Nav></View>
      ))}
      <Gap /><Nav href="/shops/new">+ Add a shop</Nav>
      <Gap /><Btn title="Refresh" onPress={reload} />
      <Btn title="Sign out" onPress={signOut} />
    </Screen>
  );
}
