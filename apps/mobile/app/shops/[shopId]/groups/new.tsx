import { useState } from "react";
import { View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Text, Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";

export default function NewGroup() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const router = useRouter();
  const offers = useLoad<any[]>("/marketplace/offers/", true);
  const [offer, setOffer] = useState<any>(null);
  const [target, setTarget] = useState(""); const [mine, setMine] = useState("");
  const [deadline, setDeadline] = useState("");
  const [method, setMethod] = useState<"delivery" | "collection">("delivery");
  const [point, setPoint] = useState(""); const [fee, setFee] = useState("0"); const [note, setNote] = useState("");
  const [key] = useState(uuid());
  const { busy, error, run } = useAction();
  const create = () => run(async () => {
    const g = await api(`/shops/${shopId}/group-orders/`, { method: "POST", body: {
      idempotency_key: key, offer_id: offer.id, target_quantity: target, quantity: mine,
      deadline: new Date(deadline).toISOString(), delivery_method: method, delivery_point: point,
      estimated_delivery_fee: fee, note } });
    router.replace(`/shops/${shopId}/groups/${g.id}`);
  });
  return (
    <Screen title="Start a group buy">
      <Text>Pool an order with nearby shops to reach a cheaper volume price. Nothing is binding until the wholesaler confirms.</Text>
      {!offer ? <>
        <Loading loading={offers.loading} error={offers.error} />
        {offers.data?.filter((o) => o.tiers?.length).map((o) => (
          <View key={o.id}><Btn title={`${o.product.name} per ${o.unit.unit_name} - ${o.wholesaler.business_name} (${o.tiers.length} price tiers)`} onPress={() => setOffer(o)} /></View>
        ))}
        {offers.data && !offers.data.some((o) => o.tiers?.length) ? <Text>No offers with volume prices yet.</Text> : null}
      </> : <>
        <Text>{offer.product.name} per {offer.unit.unit_name} from {offer.wholesaler.business_name} (list {offer.currency} {offer.price_per_unit})</Text>
        {offer.tiers.map((t: any, i: number) => <Text key={i}>  {t.minimum_quantity}+ at {t.unit_price}</Text>)}
        <Field label={`Target quantity (${offer.unit.unit_name})`} value={target} onChangeText={setTarget} keyboardType="numeric" />
        <Field label="Your own quantity" value={mine} onChangeText={setMine} keyboardType="numeric" />
        <Field label="Deadline (YYYY-MM-DD HH:MM)" value={deadline} onChangeText={setDeadline} placeholder="2026-11-05 18:00" />
        <Btn title={`Method: ${method} (tap to switch)`} onPress={() => setMethod(method === "delivery" ? "collection" : "delivery")} />
        <Field label={method === "delivery" ? "Delivery point" : "Collection point"} value={point} onChangeText={setPoint} />
        <Field label="Estimated delivery fee (KES)" value={fee} onChangeText={setFee} keyboardType="numeric" />
        <Field label="Note (optional)" value={note} onChangeText={setNote} />
        <ErrorText error={error} /><Gap />
        <Btn title="Create group" disabled={busy} onPress={create} />
        <Btn title="Pick another offer" onPress={() => setOffer(null)} />
      </>}
    </Screen>
  );
}
