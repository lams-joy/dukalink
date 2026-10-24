import { Text } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { useFocusEffect } from "expo-router";
import { Screen, Nav, Gap, Loading, useLoad } from "../../../src/ui";
import { flush, queueFor } from "../../../src/offline";

export default function ShopHome() {
  const { shopId } = useLocalSearchParams<{ shopId: string }>();
  const shop = useLoad<any>(`/shops/${shopId}/`);
  const sum = useLoad<any>(`/shops/${shopId}/reports/summary/`);
  const s = sum.data;
  const [waiting, setWaiting] = useState(0);
  useFocusEffect(useCallback(() => { (async () => { try { await flush(shopId!); } catch {} setWaiting((await queueFor(shopId!)).length); })(); }, [shopId]));
  const base = `/shops/${shopId}`;
  return (
    <Screen title={shop.data?.name ?? "Shop"}>
      <Loading loading={shop.loading || sum.loading} error={shop.error ?? sum.error} />
      {s ? (
        <>
          <Text>Period: {s.period.from} to {s.period.to}</Text>
          <Text>Tracked products: {s.stock.tracked_products} | Low: {s.stock.low_stock_count} | Out: {s.stock.out_of_stock_count}</Text>
          <Text>Sales: {s.sales.count} totalling KES {s.sales.total_amount}</Text>
          <Text>Purchases: {s.purchases.count} totalling KES {s.purchases.total_cost}</Text>
          {s.top_selling.map((t: any) => <Text key={t.shop_product_id}>Top: {t.product_name} - {t.quantity_base} (KES {t.revenue})</Text>)}
        </>
      ) : null}
      {waiting ? <Nav href={`/shops/${shopId}/queue`}>{waiting} record(s) waiting to sync - tap to review</Nav> : null}
      <Gap />
      <Text>Stock</Text>
      <Nav href={`${base}/inventory`}>Inventory</Nav>
      <Nav href={`${base}/inventory/add`}>Track a catalogue product</Nav>
      <Nav href={`${base}/inventory/new-product`}>Add my own product</Nav>
      <Nav href={`${base}/counts`}>Stock counts</Nav>
      <Nav href={`${base}/sell`}>Record a sale</Nav>
      <Nav href={`${base}/receive`}>Record goods received</Nav>
      <Nav href={`${base}/alerts`}>Low-stock alerts</Nav>
      <Nav href={`${base}/movements`}>Stock movements</Nav>
      <Gap /><Text>Buying</Text>
      <Nav href={`${base}/market`}>Marketplace offers</Nav>
      <Nav href={`${base}/market/wholesalers`}>Verified wholesalers</Nav>
      <Nav href={`${base}/orders`}>My orders</Nav>
      <Nav href={`${base}/groups`}>Group buying</Nav>
      <Gap /><Nav href={`${base}/queue`}>Waiting to sync</Nav>
      <Nav href={`${base}/settings`}>Shop settings and team</Nav>
      <Nav href="/shops">All shops</Nav>
    </Screen>
  );
}
