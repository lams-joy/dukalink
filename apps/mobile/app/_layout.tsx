import { useEffect } from "react";
import { Slot, useGlobalSearchParams, useRouter, useSegments } from "expo-router";
import { ActivityIndicator, Pressable, View } from "react-native";
import { useFonts } from "expo-font";
import { Feather } from "@expo/vector-icons";
import { AuthProvider, useAuth } from "../src/auth";
import { Backdrop, BottomNav, Glass, Icon, Text } from "../src/ui";
import { theme as t } from "../src/theme";

function TopBar() {
  const router = useRouter();
  const segments = useSegments();
  const atRoot = segments.length <= 1 && segments[0] === "shops";
  return (
    <View style={{ alignItems: "center", paddingHorizontal: 12, paddingTop: 12 }}>
      <Glass pad={8} radius={26} strong style={{ width: "100%", maxWidth: t.maxWidth }}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace("/shops"))} disabled={atRoot} accessibilityLabel="Back"
            style={{ width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", backgroundColor: atRoot ? "transparent" : "rgba(255,255,255,0.7)" }}>
            {atRoot ? null : <Icon name="chevron-left" size={22} />}
          </Pressable>
          <Text style={{ fontWeight: "900", fontSize: 18, letterSpacing: -0.6, marginBottom: 0, color: t.color.primaryDark }}>DukaLink</Text>
          <Pressable onPress={() => router.replace("/shops")} accessibilityLabel="My shops"
            style={{ width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.7)" }}>
            <Icon name="grid" size={18} />
          </Pressable>
        </View>
      </Glass>
    </View>
  );
}

function Guard() {
  const { ready, user } = useAuth();
  const [fontsReady] = useFonts(Feather.font);
  const segments = useSegments();
  const router = useRouter();
  const { shopId } = useGlobalSearchParams<{ shopId?: string }>();
  const inPublic = segments[0] === "login" || segments[0] === "register";
  useEffect(() => {
    if (!ready) return;
    if (!user && !inPublic) router.replace("/login");
    if (user && inPublic) router.replace("/shops");
  }, [ready, user, segments]);
  const inShop = user && shopId && segments[0] === "shops" && (segments as string[])[1] === "[shopId]";
  return (
    <View style={{ flex: 1, backgroundColor: t.backdrop[0] }}>
      <Backdrop />
      {!ready || !fontsReady ? <ActivityIndicator color={t.color.primary} style={{ marginTop: 120 }} /> : (
        <>
          {user ? <TopBar /> : null}
          <View style={{ flex: 1 }}><Slot /></View>
          {inShop ? <BottomNav shopId={shopId!} /> : null}
        </>
      )}
    </View>
  );
}
export default function Root() {
  return <AuthProvider><Guard /></AuthProvider>;
}
