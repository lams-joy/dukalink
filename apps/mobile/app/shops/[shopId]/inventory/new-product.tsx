import { useState } from "react";
import { Text } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Screen, Field, Btn, ErrorText, Gap, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";

type U = { unit_name: string; base_quantity: string };
export default function NewProduct() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const router = useRouter();
  const [name, setName] = useState(""); const [base_unit, setBase] = useState("");
  const [brand, setBrand] = useState(""); const [category, setCategory] = useState("");
  const [reorder, setReorder] = useState("");
  const [units, setUnits] = useState<U[]>([]);
  const [key] = useState(uuid());
  const { busy, error, run } = useAction();
  const setU = (i: number, k: keyof U, v: string) => setUnits(units.map((u, j) => (j === i ? { ...u, [k]: v } : u)));
  const save = () => run(async () => {
    await api(`/shops/${shopId}/products/`, { method: "POST", body: {
      idempotency_key: key, name, base_unit, brand, category, track: true,
      ...(reorder ? { reorder_level_base: reorder } : {}),
      units: units.filter((u) => u.unit_name && u.base_quantity) } });
    router.replace(`/shops/${shopId}/inventory`);
  });
  return (
    <Screen title="Add your own product">
      <Text>For items not in the catalogue. The base unit is the smallest thing you count (kg, litre, piece).</Text>
      <Field label="Name" value={name} onChangeText={setName} autoCapitalize="words" />
      <Field label="Base unit (kg, litre, piece...)" value={base_unit} onChangeText={setBase} />
      <Field label="Brand (optional)" value={brand} onChangeText={setBrand} />
      <Field label="Category (optional)" value={category} onChangeText={setCategory} />
      <Field label="Reorder level in base units (optional)" value={reorder} onChangeText={setReorder} keyboardType="numeric" />
      <Gap /><Text>Other units you buy or sell in (e.g. sack = 50 kg):</Text>
      {units.map((u, i) => (<>
        <Field key={`n${i}`} label="Unit name" value={u.unit_name} onChangeText={(v) => setU(i, "unit_name", v)} />
        <Field key={`q${i}`} label={`How many ${base_unit || "base units"} in one`} value={u.base_quantity} onChangeText={(v) => setU(i, "base_quantity", v)} keyboardType="numeric" />
      </>))}
      <Btn title="+ Add a unit" onPress={() => setUnits([...units, { unit_name: "", base_quantity: "" }])} />
      <ErrorText error={error} /><Gap />
      <Btn title="Save product" disabled={busy} onPress={save} />
    </Screen>
  );
}
