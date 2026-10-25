import { useEffect, useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Text, Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../src/ui";
import { api } from "../../../src/api";

export default function Settings() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const { data: shop, error, loading, reload } = useLoad<any>(`/shops/${shopId}/`);
  const audit = useLoad<any[]>(`/shops/${shopId}/audit-events/`, true);
  const [name, setName] = useState(""); const [loc, setLoc] = useState(""); const [tz, setTz] = useState(""); const [mode, setMode] = useState("transaction");
  const [phone, setPhone] = useState(""); const [role, setRole] = useState<"manager" | "staff">("staff");
  const save = useAction(); const add = useAction(); const onb = useAction();
  const [added, setAdded] = useState<string | null>(null);
  useEffect(() => { if (shop) { setName(shop.name); setLoc(shop.location_text); setTz(shop.timezone); setMode(shop.default_tracking_mode); } }, [shop]);

  const saveShop = () => save.run(async () => { await api(`/shops/${shopId}/`, { method: "PATCH", body: { name, location_text: loc, timezone: tz, default_tracking_mode: mode } }); reload(); });
  const addMember = () => add.run(async () => { await api(`/shops/${shopId}/members/`, { method: "POST", body: { phone_number: phone, role } }); setAdded(`Added ${phone} as ${role}.`); setPhone(""); });
  const finish = () => onb.run(async () => { await api(`/shops/${shopId}/onboarding/complete/`, { method: "POST", body: {} }); reload(); });

  return (
    <Screen title="Shop settings">
      <Loading loading={loading} error={error} />
      {shop ? <>
        <Field label="Shop name" value={name} onChangeText={setName} autoCapitalize="words" />
        <Field label="Location" value={loc} onChangeText={setLoc} />
        <Field label="Timezone" value={tz} onChangeText={setTz} placeholder="Africa/Nairobi" />
        <Btn title={`New products are tracked by: ${mode} (tap to switch simple/transaction)`} onPress={() => setMode(mode === "simple" ? "transaction" : "simple")} />
        <ErrorText error={save.error} /><Btn title="Save shop" disabled={save.busy} onPress={saveShop} />
        <Gap />{shop.onboarding_completed_at ? <Text>Setup finished.</Text> : <><Btn title="Finish setup" disabled={onb.busy} onPress={finish} /><ErrorText error={onb.error} /></>}
        <Gap /><Text>Add a team member (they must already have an account)</Text>
        <Field label="Their phone number" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
        <Btn title={`Role: ${role} (tap to switch)`} onPress={() => setRole(role === "staff" ? "manager" : "staff")} />
        <ErrorText error={add.error} />{added ? <Text>{added}</Text> : null}
        <Btn title="Add member" disabled={add.busy || !phone} onPress={addMember} />
      </> : null}
      <Gap /><Text>Activity log</Text>
      <Loading loading={audit.loading} error={audit.error} />
      {audit.data?.map((a) => <View key={a.id}><Text>{new Date(a.created_at).toLocaleString()} - {a.action} {a.object_type}</Text></View>)}
    </Screen>
  );
}
