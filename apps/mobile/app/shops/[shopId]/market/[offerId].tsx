import { useState } from "react";
import { Text } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";

export default function Offer() {
  const { shopId, offerId } = useLocalSearchParams<{ shopId: string; offerId: string }>();
  const router = useRouter();
  const { data: o, error, loading } = useLoad<any>(`/marketplace/offers/${offerId}/`);
  const [qty, setQty] = useState("");
  const [quote, setQuote] = useState<any>(null);
  const [address, setAddress] = useState("");
  const [key] = useState(uuid());
  const [method, setMethod] = useState<"delivery" | "collection">("delivery");
  const q = useAction();
  const order = useAction();

  const getQuote = () => q.run(async () => setQuote(await api(`/marketplace/offers/${offerId}/quote/?quantity=${encodeURIComponent(qty)}`)));
  const place = () => order.run(async () => {
    await api(`/shops/${shopId}/orders/`, {
      method: "POST",
      body: { idempotency_key: key, items: [{ offer_id: offerId, quantity: qty }], delivery_method: method, delivery_address: method === "delivery" ? address : "" },
    });
    router.replace(`/shops/${shopId}/orders`);
  });

  return (
    <Screen title={o?.product?.name ?? "Offer"}>
      <Loading loading={loading} error={error} />
      {o ? <>
        <Text>From {o.wholesaler.business_name} ({o.wholesaler.location_text})</Text>
        <Text>{o.currency} {o.price_per_unit} per {o.unit?.unit_name} | minimum {o.minimum_order_quantity} | {o.availability}</Text>
        <Text>Delivery: {o.delivery_areas || "-"} {o.delivery_terms || ""}</Text>
        {o.tiers?.map((t: any, i: number) => <Text key={i}>Buy {t.minimum_quantity}+ at {o.currency} {t.unit_price}</Text>)}
        <Gap />
        <Field label={`Quantity (${o.unit?.unit_name ?? "units"})`} value={qty} onChangeText={setQty} keyboardType="numeric" />
        <Btn title="Get price" onPress={getQuote} /><ErrorText error={q.error} />
        {quote ? <Text>{quote.quantity} x {quote.unit_price} = {quote.currency} {quote.line_total}{quote.meets_minimum ? "" : " (below the minimum order)"}</Text> : null}
        <Gap /><Btn title={`Method: ${method} (tap to switch)`} onPress={() => setMethod(method === "delivery" ? "collection" : "delivery")} />
        {method === "delivery" ? <Field label="Delivery address" value={address} onChangeText={setAddress} /> : null}
        <ErrorText error={order.error} />
        <Btn title="Place order" disabled={order.busy || !qty} onPress={place} />
      </> : null}
    </Screen>
  );
}
