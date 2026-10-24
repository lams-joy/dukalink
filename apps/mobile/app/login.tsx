import { useState } from "react";
import { Screen, Field, Btn, ErrorText, Nav, Gap, useAction } from "../src/ui";
import { useAuth } from "../src/auth";

export default function Login() {
  const { signIn } = useAuth();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();
  return (
    <Screen title="DukaLink - Sign in">
      <Field label="Phone number" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="0712345678" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry />
      <ErrorText error={error} /><Gap />
      <Btn title={busy ? "Signing in..." : "Sign in"} disabled={busy} onPress={() => run(() => signIn(phone, password))} />
      <Gap /><Nav href="/register">Create an account</Nav>
    </Screen>
  );
}
