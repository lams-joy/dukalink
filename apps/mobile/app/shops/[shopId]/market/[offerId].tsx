import { useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Screen, Text, View, Glass, Icon, Section, Pill, Avatar, Field, Btn, ErrorText, Gap, kes, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";
import { theme as t } from "../../../../src/theme";

export default function Offer() {
  const { shopId, offerId } = useLocalSearchParams<{ shopId: string; offerId: string }>();
  const router = useRouter();
  const { data: o, error, loading } = useLoad<any>(`/marketplace/offers/${offerId}/`);
  const [qty, setQty] = useState("");
  const [quote, setQuote] = useState<any>(null);
  const [address, setAddress] = useState("");
  const [method, setMethod] = useState<"delivery" | "collection">("delivery");
  const [key] = useState(uuid());
  const q = useAction();
  const order = useAction();

  const getQuote = () => q.run(async () => setQuote(await api(`/marketplace/offers/${offerId}/quote/?quantity=${encodeURIComponent(qty)}`)));
  const place = () => order.run(async () => {
    await api(`/shops/${shopId}/orders/`, { method: "POST", body: { idempotency_key: key, items: [{ offer_id: offerId, quantity: qty }],
      delivery_method: method, delivery_address: method === "delivery" ? address : "" } });
    router.replace(`/shops/${shopId}/orders`);
  });

  return (
    <Screen>
      <Loading loading={loading} error={error} />
      {o ? <>
        <Glass pad={18} radius={24}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: t.space.md }}>
            <Avatar name={o.product?.name ?? "?"} size={64} />
            <View style={{ marginLeft: t.space.md, flex: 1 }}>
              <Text style={{ fontSize: 22, fontWeight: "800", marginBottom: 2 }}>{o.product?.name}</Text>
              <Text style={{ color: t.color.muted, marginBottom: 0 }}>{o.wholesaler.business_name} - {o.wholesaler.location_text}</Text>
            </View>
          </View>
          <Text style={{ fontSize: 30, fontWeight: "900", color: t.color.primary, marginBottom: 0 }}>{o.currency} {Number(o.price_per_unit).toLocaleString()}
            <Text style={{ fontSize: 14, color: t.color.muted, fontWeight: "400" }}> per {o.unit?.unit_name}</Text></Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: t.space.sm }}>
            <Pill tone={o.availability === "in_stock" ? "good" : o.availability === "limited" ? "warn" : "bad"}>{String(o.availability).replace("_", " ")}</Pill>
            <Pill>Minimum {o.minimum_order_quantity}</Pill>
          </View>
          {o.delivery_areas || o.delivery_terms ? <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}><Icon name="truck" size={16} color={t.color.muted} /><Text style={{ color: t.color.muted, marginBottom: 0, marginLeft: 8, flex: 1 }}>{o.delivery_areas} {o.delivery_terms}</Text></View> : null}
        </Glass>

        {o.tiers?.length ? <>
          <Section>Buy more, pay less</Section>
          <Glass pad={18} radius={24}>{o.tiers.map((x: any, i: number) => (
            <View key={i} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderTopWidth: i ? 1 : 0, borderTopColor: t.color.border }}>
              <Text style={{ marginBottom: 0 }}>{x.minimum_quantity}+ {o.unit?.unit_name}</Text>
              <Text style={{ fontWeight: "800", marginBottom: 0 }}>{o.currency} {Number(x.unit_price).toLocaleString()} each</Text>
            </View>))}</Glass>
        </> : null}

        <Section>Order this</Section>
        <Glass pad={18} radius={24}>
          <Field label={`How many (${o.unit?.unit_name ?? "units"})`} value={qty} onChangeText={setQty} keyboardType="numeric" />
          <Btn kind="plain" title="See my price" onPress={getQuote} disabled={!qty} /><ErrorText error={q.error} />
          {quote ? <View style={{ backgroundColor: t.color.primarySoft, borderRadius: t.radius, padding: t.space.md, marginBottom: t.space.md }}>
            <Text style={{ marginBottom: 0 }}>{quote.quantity} x {kes(quote.unit_price)}</Text>
            <Text style={{ fontSize: 22, fontWeight: "800", color: t.color.primary, marginBottom: 0 }}>{kes(quote.line_total)}</Text>
            {quote.meets_minimum ? null : <Text style={{ color: t.color.danger, marginBottom: 0 }}>Below the minimum order.</Text>}
          </View> : null}
          <View style={{ flexDirection: "row" }}>
            <View style={{ flex: 1, marginRight: 6 }}><Btn kind={method === "delivery" ? "primary" : "plain"} icon="truck" title="Delivery" onPress={() => setMethod("delivery")} /></View>
            <View style={{ flex: 1 }}><Btn kind={method === "collection" ? "primary" : "plain"} icon="shopping-bag" title="Collect" onPress={() => setMethod("collection")} /></View>
          </View>
          {method === "delivery" ? <Field label="Delivery address" value={address} onChangeText={setAddress} /> : null}
          <ErrorText error={order.error} />
          <Btn title="Place order" disabled={order.busy || !qty} onPress={place} />
        </Glass>
      </> : null}
    </Screen>
  );
}
