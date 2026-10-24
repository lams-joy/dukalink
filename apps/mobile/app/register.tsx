import { useState } from "react";
import { useRouter } from "expo-router";
import { Screen, Field, Btn, ErrorText, Nav, Gap, useAction } from "../src/ui";
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
    <Screen title="Create account">
      <Field label="Full name" value={full_name} onChangeText={setName} autoCapitalize="words" />
      <Field label="Phone number" value={phone_number} onChangeText={setPhone} keyboardType="phone-pad" />
      <Field label="Password (long, not common)" value={password} onChangeText={setPassword} secureTextEntry />
      <ErrorText error={error} /><Gap />
      <Btn title={busy ? "Creating..." : "Register"} disabled={busy} onPress={submit} />
      <Gap /><Nav href="/login">Back to sign in</Nav>
    </Screen>
  );
}
