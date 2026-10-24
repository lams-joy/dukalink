import { useState } from "react";
import { Text } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { Screen, Field, Btn, ErrorText, Gap, Loading, useLoad, useAction } from "../../../../src/ui";
import { api, uuid } from "../../../../src/api";

export default function Group() {
  const { shopId, groupId } = useLocalSearchParams<{ shopId: string; groupId: string }>();
  const base = `/shops/${shopId}/group-orders/${groupId}`;
  const { data: g, error, loading, reload } = useLoad<any>(`${base}/`);
  const [qty, setQty] = useState("");
  const act = useAction();
  const open = g?.status === "open";
  const join = () => act.run(async () => {
    const body = { quantity: qty, product_unit_id: g.product_unit_id };
    if (g.my_commitment) await api(`${base}/my-commitment/`, { method: "PATCH", body: { quantity: qty } });
    else await api(`${base}/join/`, { method: "POST", body: { idempotency_key: uuid(), ...body } });
    reload();
  });
  const costs = useLoad<any>(g?.binding ? `${base}/cost-breakdown/` : null);
  const [why, setWhy] = useState("");
  const close = () => act.run(async () => { await api(`${base}/close/`, { method: "POST", body: {} }); reload(); });
  const cancel = () => act.run(async () => { await api(`${base}/cancel/`, { method: "POST", body: { reason: why } }); reload(); });
  const withdraw = () => act.run(async () => { await api(`${base}/withdraw/`, { method: "POST", body: {} }); reload(); });
  return (
    <Screen title={g?.product_name ?? "Group"}>
      <Loading loading={loading} error={error} />
      {g ? <>
        <Text>Status: {g.status}{g.status_note ? ` - ${g.status_note}` : ""}</Text>
        <Text>Wholesaler: {g.wholesaler?.business_name}</Text>
        <Text>Committed {g.committed_quantity} of {g.target_quantity} {g.unit_name} from {g.participant_count} shops</Text>
        <Text>List price {g.currency} {g.list_price} | at target about {g.unit_price_at_target ?? "-"} | now about {g.estimated_unit_price ?? "-"}</Text>
        <Text>Deadline: {new Date(g.deadline).toLocaleString()} | Minimum per shop: {g.minimum_per_shop}</Text>
        <Text>Your commitment: {g.my_commitment ? JSON.stringify(g.my_commitment) : "none"}{g.is_organiser ? " (you organised this)" : ""}</Text>
        {g.binding ? <Text>Confirmed terms: {JSON.stringify(g.terms)}</Text> : <Text>Not binding until the wholesaler confirms.</Text>}
        <Gap />
        {open ? <>
          <Field label={`${g.my_commitment ? "Change" : "Join with"} quantity (${g.unit_name})`} value={qty} onChangeText={setQty} keyboardType="numeric" />
          <Btn title={g.my_commitment ? "Update commitment" : "Join group"} disabled={act.busy} onPress={join} />
          {g.my_commitment && !g.is_organiser ? <Btn title="Withdraw" onPress={withdraw} /> : null}
        </> : null}
        {g.is_organiser && ["open", "closed"].includes(g.status) ? <>
          <Gap /><Text>You organised this group.</Text>
          {open ? <Btn title="Close early and send to the wholesaler" disabled={act.busy} onPress={close} /> : null}
          <Field label="Reason for cancelling" value={why} onChangeText={setWhy} />
          <Btn title="Cancel group" disabled={act.busy || !why} onPress={cancel} />
        </> : null}
        {costs.data ? <><Gap /><Text>Your cost breakdown: {JSON.stringify(costs.data)}</Text></> : null}
        <ErrorText error={act.error} />
      </> : null}
    </Screen>
  );
}
