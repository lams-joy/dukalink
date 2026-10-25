import { useState } from "react";
import { Pressable } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Screen, Text, View, Glass, Grid, Pill, Avatar, Banner, Section, Field, Btn, ErrorText, Gap, Icon, kes, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";
import { theme as t } from "../../../../src/theme";

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

  // Offers with bulk prices first: those are the ones where pooling actually lowers the price.
  const all = [...(offers.data ?? [])].sort((a, b) => (b.tiers?.length ? 1 : 0) - (a.tiers?.length ? 1 : 0));
  const anyTiers = all.some((o) => o.tiers?.length);
  const hasTiers = !!offer?.tiers?.length;

  const create = () => run(async () => {
    const g = await api(`/shops/${shopId}/group-orders/`, { method: "POST", body: {
      idempotency_key: key, offer_id: offer.id, target_quantity: target, quantity: mine,
      deadline: new Date(deadline.replace(" ", "T")).toISOString(), delivery_method: method, delivery_point: point,
      estimated_delivery_fee: fee, note } });
    router.replace(`/shops/${shopId}/groups/${g.id}`);
  });

  return (
    <Screen title="Start a group buy" subtitle="Pool an order with nearby shops to reach a cheaper volume price. Nothing is binding until the wholesaler confirms.">
      {!offer ? <>
        <Loading loading={offers.loading} error={offers.error} />

        {!offers.loading && !offers.error && all.length === 0 ? (
          <Glass pad={20} radius={18}>
            <Text style={{ fontWeight: "800", fontSize: 18, letterSpacing: -0.3 }}>There is nothing to buy in bulk yet</Text>
            <Text style={{ color: t.color.muted }}>Group buys are made on a wholesaler's offer. None are available right now. For offers to appear:</Text>
            <Text>1. A wholesaler registers a business in the wholesaler portal.</Text>
            <Text>2. The platform administrator verifies that business.</Text>
            <Text>3. The wholesaler creates offers and adds volume prices to them.</Text>
            <Text style={{ color: t.color.muted, marginBottom: 0 }}>Check back after that, or browse the Marketplace.</Text>
          </Glass>
        ) : null}

        {all.length > 0 && !anyTiers ? (
          <Banner tone="info" icon="info">None of these offers has volume prices yet, so a group would not lower the price. Ask the wholesaler to add bulk prices to an offer in their portal (Offers, then Volume prices).</Banner>
        ) : null}

        {all.length > 0 ? <Section>Choose an offer</Section> : null}
        <Grid min={300}>
          {all.map((o) => (
            <Pressable key={o.id} onPress={() => setOffer(o)} style={({ pressed }) => ({ transform: [{ scale: pressed ? 0.985 : 1 }] })}>
              <Glass pad={14} radius={14}>
                <View style={{ flexDirection: "row", alignItems: "center" }}>
                  <Avatar name={o.product?.name ?? "?"} size={46} />
                  <View style={{ flex: 1, marginLeft: 12 }}>
                    <Text style={{ fontWeight: "700", fontSize: 16, letterSpacing: -0.2, marginBottom: 0 }}>{o.product?.name} <Text style={{ color: t.color.muted, fontWeight: "500" }}>per {o.unit?.unit_name}</Text></Text>
                    <Text style={{ color: t.color.muted, fontSize: t.font.small, marginBottom: 4 }}>{o.wholesaler.business_name} - {kes(o.price_per_unit)}</Text>
                    <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
                      {o.tiers?.length ? <Pill tone="good">{o.tiers.length} bulk price{o.tiers.length > 1 ? "s" : ""}</Pill> : <Pill>No bulk price</Pill>}
                      <Pill>Min {o.minimum_order_quantity}</Pill>
                    </View>
                  </View>
                  <Icon name="chevron-right" size={18} color={t.color.faint} />
                </View>
              </Glass>
            </Pressable>
          ))}
        </Grid>
      </> : <>
        <Glass pad={16} radius={14} style={{ marginBottom: t.space.md }}>
          <View style={{ flexDirection: "row", alignItems: "center" }}>
            <Avatar name={offer.product.name} size={44} />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={{ fontWeight: "700", fontSize: 16, marginBottom: 0 }}>{offer.product.name} per {offer.unit.unit_name}</Text>
              <Text style={{ color: t.color.muted, marginBottom: 0 }}>{offer.wholesaler.business_name} - list price {kes(offer.price_per_unit)}</Text>
            </View>
          </View>
          {hasTiers ? <View style={{ marginTop: 10 }}>
            {offer.tiers.map((x: any, i: number) => <Text key={i} style={{ marginBottom: 2 }}>{x.minimum_quantity}+ {offer.unit.unit_name}: <Text style={{ fontWeight: "800" }}>{kes(x.unit_price)}</Text> each</Text>)}
          </View> : null}
        </Glass>

        {!hasTiers ? <Banner icon="alert-triangle">This offer has no volume prices, so pooling will not lower the price. You can still start the group.</Banner> : null}

        <Glass pad={18} radius={14}>
          <Field label={`Target quantity (${offer.unit.unit_name})`} value={target} onChangeText={setTarget} keyboardType="numeric" />
          <Field label="Your own quantity" value={mine} onChangeText={setMine} keyboardType="numeric" />
          <Field label="Deadline (YYYY-MM-DD HH:MM)" value={deadline} onChangeText={setDeadline} placeholder="2026-11-05 18:00" />
          <View style={{ flexDirection: "row" }}>
            <View style={{ flex: 1, marginRight: 6 }}><Btn kind={method === "delivery" ? "primary" : "plain"} icon="truck" title="Delivery" onPress={() => setMethod("delivery")} /></View>
            <View style={{ flex: 1 }}><Btn kind={method === "collection" ? "primary" : "plain"} icon="shopping-bag" title="Collect" onPress={() => setMethod("collection")} /></View>
          </View>
          <Field label={method === "delivery" ? "Delivery address" : "Collection point"} value={point} onChangeText={setPoint} />
          <Field label="Estimated delivery fee (KES)" value={fee} onChangeText={setFee} keyboardType="numeric" />
          <Field label="Note (optional)" value={note} onChangeText={setNote} />
          <ErrorText error={error} /><Gap />
          <Btn title="Create group" disabled={busy || !target || !mine || !deadline || !point} onPress={create} />
          <Btn kind="plain" title="Pick another offer" onPress={() => setOffer(null)} />
        </Glass>
      </>}
    </Screen>
  );
}
