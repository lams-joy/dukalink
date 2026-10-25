import { Pressable } from "react-native";
import { Link } from "expo-router";
import { Screen, Text, View, Glass, Grid, Avatar, Pill, Btn, Icon, Gap, Loading, useLoad } from "../../src/ui";
import { useAuth } from "../../src/auth";
import { theme as t } from "../../src/theme";

export default function Shops() {
  const { user, signOut } = useAuth();
  const { data, error, loading } = useLoad<any[]>("/shops/", true);
  return (
    <Screen title={`Hello, ${user?.full_name?.split(" ")[0] ?? ""}`} subtitle="Choose a shop to manage, or add a new one.">
      <Loading loading={loading} error={error} />
      <Grid min={280}>
        {[...(data ?? []).map((s) => (
          <Link key={s.id} href={`/shops/${s.id}`} asChild>
            <Pressable style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.985 : 1 }] })}>
              <Glass pad={16} radius={14}>
                <View style={{ flexDirection: "row", alignItems: "center" }}>
                  <Avatar name={s.name} size={54} />
                  <View style={{ marginLeft: 14, flex: 1 }}>
                    <Text style={{ fontWeight: "800", fontSize: 18, letterSpacing: -0.4, marginBottom: 0 }}>{s.name}</Text>
                    <Text style={{ color: t.color.muted, marginBottom: 6 }}>{s.location_text}</Text>
                    <Pill tone="good">{s.my_role}</Pill>
                  </View>
                  <Icon name="chevron-right" size={20} color={t.color.faint} />
                </View>
              </Glass>
            </Pressable>
          </Link>)),
          <Link key="new" href="/shops/new" asChild>
            <Pressable style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.985 : 1 }] })}>
              <Glass pad={16} radius={14} style={{ borderStyle: "dashed" }}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", height: 54 }}>
                  <Icon name="plus" size={20} color={t.color.primaryDark} />
                  <Text style={{ fontWeight: "700", marginBottom: 0, marginLeft: 8, color: t.color.primaryDark }}>Add a shop</Text>
                </View>
              </Glass>
            </Pressable>
          </Link>]}
      </Grid>
      <Gap /><Btn kind="plain" icon="log-out" title="Sign out" onPress={signOut} />
    </Screen>
  );
}
