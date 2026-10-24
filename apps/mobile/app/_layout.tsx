import { useEffect } from "react";
import { Slot, useRouter, useSegments } from "expo-router";
import { ActivityIndicator } from "react-native";
import { AuthProvider, useAuth } from "../src/auth";

function Guard() {
  const { ready, user } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    const inPublic = segments[0] === "login" || segments[0] === "register";
    if (!user && !inPublic) router.replace("/login");
    if (user && inPublic) router.replace("/shops");
  }, [ready, user, segments]);
  return ready ? <Slot /> : <ActivityIndicator />;
}
export default function Root() {
  return <AuthProvider><Guard /></AuthProvider>;
}
