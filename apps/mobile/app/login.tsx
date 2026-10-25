import { useState } from "react";
import { Screen, Text, View, Glass, Field, Btn, ErrorText, Nav, Gap, useAction } from "../src/ui";
import { useAuth } from "../src/auth";

export default function Login() {
  const { signIn } = useAuth();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
  return (
    <Screen>
      <Brand sub="Sign in to manage your duka" />
      <Glass pad={24} radius={18} strong>
      <Field label="Phone number" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="0712345678" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry />
      <ErrorText error={error} /><Gap />
      <Btn title={busy ? "Signing in..." : "Sign in"} disabled={busy} onPress={() => run(() => signIn(phone, password))} />
      <Gap /><Nav href="/register">Create an account</Nav>
      </Glass>
    </Screen>
  );
}

function Brand({ sub }: { sub: string }) {
  return (
    <View style={{ alignItems: "center", marginTop: 40, marginBottom: 28 }}>
      <View style={{ width: 64, height: 64, borderRadius: 14, alignItems: "center", justifyContent: "center", marginBottom: 14, backgroundColor: "#0E9F6E", boxShadow: "0 12px 28px rgba(14,159,110,0.45)" }}>
        <Text style={{ color: "#fff", fontSize: 30, fontWeight: "900", marginBottom: 0, lineHeight: 36 }}>D</Text>
      </View>
      <Text style={{ fontSize: 34, fontWeight: "900", letterSpacing: -1.2, lineHeight: 40, marginBottom: 2 }}>DukaLink</Text>
      <Text style={{ color: "#5B6B66", marginBottom: 0 }}>{sub}</Text>
    </View>
  );
}
