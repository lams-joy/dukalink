import { useCallback, useState } from "react";
import { Pressable } from "react-native";
import { Link, useFocusEffect, useLocalSearchParams } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Screen, Text, View, Glass, Grid, Stat, Tile, Section, Banner, Icon, kes, Loading, useLoad } from "../../../src/ui";
import { flush, queueFor } from "../../../src/offline";
import { theme as t } from "../../../src/theme";

export default function ShopHome() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const shop = useLoad<any>(`/shops/${shopId}/`);
  const sum = useLoad<any>(`/shops/${shopId}/reports/summary/`);
  const s = sum.data;
  const base = `/shops/${shopId}`;
  const [waiting, setWaiting] = useState(0);
  useFocusEffect(useCallback(() => { (async () => { try { await flush(shopId!); } catch {} setWaiting((await queueFor(shopId!)).length); })(); }, [shopId]));
  const low = s ? s.stock.low_stock_count : 0;
  const out = s ? s.stock.out_of_stock_count : 0;

  return (
    <Screen>
      <Loading loading={shop.loading || sum.loading} error={shop.error ?? sum.error} />

      <LinearGradient colors={t.gradient.hero} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
        style={{ borderRadius: 28, padding: 24, marginBottom: t.space.lg, overflow: "hidden", boxShadow: "0 18px 40px rgba(14,100,110,0.35)" }}>
        <View style={{ position: "absolute", right: -50, top: -60, width: 220, height: 220, borderRadius: 110, backgroundColor: "rgba(255,255,255,0.14)" }} />
        <View style={{ position: "absolute", right: 60, bottom: -90, width: 180, height: 180, borderRadius: 90, backgroundColor: "rgba(255,255,255,0.09)" }} />
        <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
          <Icon name="map-pin" size={14} color="rgba(255,255,255,0.8)" />
          <Text style={{ color: "rgba(255,255,255,0.85)", marginBottom: 0, marginLeft: 6 }}>{shop.data?.location_text}</Text>
        </View>
        <Text style={{ color: "#fff", fontSize: 26, fontWeight: "800", letterSpacing: -0.6, marginBottom: 14 }}>{shop.data?.name ?? "Your shop"}</Text>
        {s ? <>
          <Text style={{ color: "rgba(255,255,255,0.8)", fontSize: 12, fontWeight: "700", letterSpacing: 0.6, textTransform: "uppercase", marginBottom: 0 }}>Sales  {s.period.from} to {s.period.to}</Text>
          <Text style={{ color: "#fff", fontSize: 42, fontWeight: "900", letterSpacing: -1.5, lineHeight: 50, marginBottom: 0 }}>{kes(s.sales.total_amount)}</Text>
          <Text style={{ color: "rgba(255,255,255,0.85)", marginBottom: 0 }}>{s.sales.count} sales  -  {kes(s.purchases.total_cost)} bought in</Text>
        </> : null}
        <View style={{ flexDirection: "row", marginTop: 18 }}>
          <Link href={`${base}/sell`} asChild>
            <Pressable style={{ backgroundColor: "#fff", borderRadius: 16, paddingVertical: 12, paddingHorizontal: 18, marginRight: 10, flexDirection: "row", alignItems: "center", boxShadow: "0 8px 20px rgba(0,0,0,0.18)" }}>
              <Icon name="plus" size={18} color={t.color.primaryDark} /><Text style={{ color: t.color.primaryDark, fontWeight: "800", marginBottom: 0, marginLeft: 6 }}>New sale</Text>
            </Pressable></Link>
          <Link href={`${base}/receive`} asChild>
            <Pressable style={{ borderColor: "rgba(255,255,255,0.6)", borderWidth: 1, backgroundColor: "rgba(255,255,255,0.16)", borderRadius: 16, paddingVertical: 12, paddingHorizontal: 18, flexDirection: "row", alignItems: "center" }}>
              <Icon name="download" size={18} color="#fff" /><Text style={{ color: "#fff", fontWeight: "700", marginBottom: 0, marginLeft: 6 }}>Goods in</Text>
            </Pressable></Link>
        </View>
      </LinearGradient>

      {waiting ? <Banner tone="info" icon="cloud-off" href={`${base}/queue`}>{waiting} record(s) saved offline. Tap to sync.</Banner> : null}
      {low + out > 0 ? <Banner href={`${base}/alerts`}>{low} low and {out} out of stock. Tap to review.</Banner> : null}

      {s ? <Grid min={160}>
        <Stat label="Products" value={s.stock.tracked_products} icon="package" />
        <Stat label="Low stock" value={low} tone={low ? "warn" : undefined} icon="alert-triangle" />
        <Stat label="Out of stock" value={out} tone={out ? "bad" : undefined} icon="slash" />
        <Stat label="Purchases" value={s.purchases.count} icon="download" />
      </Grid> : null}

      <Section>Your stock</Section>
      <Grid min={160}>
        <Tile href={`${base}/inventory`} icon="package" label="Inventory" />
        <Tile href={`${base}/alerts`} icon="alert-triangle" label="Low-stock alerts" badge={low || undefined} />
        <Tile href={`${base}/counts`} icon="clipboard" label="Stock counts" />
        <Tile href={`${base}/movements`} icon="repeat" label="History" />
        <Tile href={`${base}/inventory/add`} icon="plus-circle" label="Add from catalogue" />
        <Tile href={`${base}/inventory/new-product`} icon="edit-3" label="Add my own product" />
      </Grid>

      <Section>Buy from wholesalers</Section>
      <Grid min={160}>
        <Tile href={`${base}/market`} icon="compass" label="Marketplace" />
        <Tile href={`${base}/groups`} icon="users" label="Group buying" />
        <Tile href={`${base}/orders`} icon="truck" label="My orders" />
        <Tile href={`${base}/market/wholesalers`} icon="briefcase" label="Wholesalers" />
      </Grid>

      {s?.top_selling?.length ? <>
        <Section>Best sellers</Section>
        <Glass pad={8} radius={22}>
          {s.top_selling.map((x: any, i: number) => (
            <View key={x.shop_product_id} style={{ flexDirection: "row", alignItems: "center", padding: 12, borderTopWidth: i ? 1 : 0, borderTopColor: t.color.line }}>
              <Text style={{ width: 26, color: t.color.faint, fontWeight: "800", marginBottom: 0 }}>{i + 1}</Text>
              <Text style={{ flex: 1, fontWeight: "600", marginBottom: 0 }}>{x.product_name}</Text>
              <Text style={{ fontWeight: "800", marginBottom: 0 }}>{kes(x.revenue)}</Text>
            </View>))}
        </Glass>
      </> : null}

      <Section>Manage</Section>
      <Grid min={160}>
        <Tile href={`${base}/settings`} icon="sliders" label="Settings and team" />
        <Tile href={`${base}/queue`} icon="cloud" label="Waiting to sync" badge={waiting || undefined} />
      </Grid>
    </Screen>
  );
}
