import { useState } from "react";
import { useRouter } from "expo-router";
import { Screen, Field, Btn, ErrorText, Gap, useAction } from "../../src/ui";
import { api } from "../../src/api";

export default function NewShop() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [location_text, setLoc] = useState("");
  const { busy, error, run } = useAction();
  const save = () => run(async () => {
    const shop = await api("/shops/", { method: "POST", body: { name, location_text } });
    router.replace(`/shops/${shop.id}`);
  });
  return (
    <Screen title="New shop">
      <Field label="Shop name" value={name} onChangeText={setName} autoCapitalize="words" />
      <Field label="Location (town / estate)" value={location_text} onChangeText={setLoc} autoCapitalize="words" />
      <ErrorText error={error} /><Gap />
      <Btn title="Save" disabled={busy} onPress={save} />
    </Screen>
  );
}
