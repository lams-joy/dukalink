import { useState } from "react";
import { useRouter } from "expo-router";
import { Screen, Text, View, Glass, Field, Btn, ErrorText, Nav, Gap, useAction } from "../src/ui";
import { api } from "../src/api";
import { useAuth } from "../src/auth";

export default function Register() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [full_name, setName] = useState("");
  const [phone_number, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
  const submit = () => run(async () => {
    await api("/auth/register/", { method: "POST", auth: false, body: { phone_number, full_name, password } });
    await signIn(phone_number, password);
    router.replace("/shops");
  });
  return (
    <Screen>
      <Brand sub="Join DukaLink - stock, sales and wholesale ordering" />
      <Glass pad={24} radius={28} strong>
      <Field label="Full name" value={full_name} onChangeText={setName} autoCapitalize="words" />
      <Field label="Phone number" value={phone_number} onChangeText={setPhone} keyboardType="phone-pad" />
      <Field label="Password (long, not common)" value={password} onChangeText={setPassword} secureTextEntry />
      <ErrorText error={error} /><Gap />
      <Btn title={busy ? "Creating..." : "Register"} disabled={busy} onPress={submit} />
      <Gap /><Nav href="/login">Back to sign in</Nav>
      </Glass>
    </Screen>
  );
}

function Brand({ sub }: { sub: string }) {
  return (
    <View style={{ alignItems: "center", marginTop: 40, marginBottom: 28 }}>
      <View style={{ width: 64, height: 64, borderRadius: 20, alignItems: "center", justifyContent: "center", marginBottom: 14, backgroundColor: "#0E9F6E", boxShadow: "0 12px 28px rgba(14,159,110,0.45)" }}>
        <Text style={{ color: "#fff", fontSize: 30, fontWeight: "900", marginBottom: 0, lineHeight: 36 }}>D</Text>
      </View>
      <Text style={{ fontSize: 34, fontWeight: "900", letterSpacing: -1.2, lineHeight: 40, marginBottom: 2 }}>DukaLink</Text>
      <Text style={{ color: "#5B6B66", marginBottom: 0 }}>{sub}</Text>
    </View>
  );
}
