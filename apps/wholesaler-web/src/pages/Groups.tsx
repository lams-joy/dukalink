import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorText, Field, Page, Status, useAction, useLoad } from "../ui";

const STATUSES = ["closed", "open", "confirmed", "declined", "failed", "cancelled"];

export function Groups() {
  const { wid } = useParams();
  const [status, setStatus] = useState("closed");
  const { data, error, loading } = useLoad<any[]>(`/wholesalers/${wid}/group-orders/?status=${status}`, true);
  return (
    <Page title="Group buys">
      <p><Link to={`/w/${wid}`}>Back</Link> | {STATUSES.map((s) => <button key={s} disabled={s === status} onClick={() => setStatus(s)}>{s}</button>)}</p>
      <p>"closed" groups reached their target and are waiting for your decision.</p>
      <Status loading={loading} error={error} />
      <ul>{data?.map((g) => (
        <li key={g.id}><Link to={`/w/${wid}/groups/${g.id}`}>{g.product_name} ({g.unit_name})</Link> - {g.committed_quantity}/{g.target_quantity} from {g.participant_count} shops - deadline {new Date(g.deadline).toLocaleString()}</li>))}</ul>
      {!loading && data?.length === 0 ? <p>None.</p> : null}
    </Page>
  );
}

export function GroupDetail() {
  const { wid, gid } = useParams();
  const base = `/wholesalers/${wid}/group-orders/${gid}`;
  const { data: g, error, loading, reload } = useLoad<any>(`${base}/`);
  const costs = useLoad<any>(g?.binding ? `${base}/cost-breakdown/` : null);
  const [price, setPrice] = useState(""); const [fee, setFee] = useState("0"); const [reason, setReason] = useState("");
  const act = useAction();
  const confirm = () => act.run(async () => { await api(`${base}/confirm/`, { method: "POST", body: { ...(price ? { unit_price: price } : {}), delivery_fee: fee } }); reload(); });
  const decline = () => act.run(async () => { await api(`${base}/decline/`, { method: "POST", body: { reason } }); reload(); });
  return (
    <Page title={g?.product_name ?? "Group buy"}>
      <p><Link to={`/w/${wid}/groups`}>Back</Link></p>
      <Status loading={loading} error={error} />
      {g ? (<>
        <p>Status: {g.status}{g.status_note ? ` - ${g.status_note}` : ""}</p>
        <p>{g.committed_quantity} of {g.target_quantity} {g.unit_name} from {g.participant_count} shops (minimum per shop {g.minimum_per_shop})</p>
        <p>List price {g.currency} {g.list_price} | price for the committed total {g.estimated_unit_price ?? "-"} | max delivery fee {g.estimated_delivery_fee}</p>
        <p>{g.delivery_method}{g.delivery_point ? `: ${g.delivery_point}` : ""} | deadline {new Date(g.deadline).toLocaleString()}</p>
        {g.status === "closed" ? (<>
          <h3>Confirming is binding: you accept the full committed quantity.</h3>
          <Field label="Unit price (blank = tier price)" value={price} onChange={(e) => setPrice(e.target.value)} />
          <Field label="Delivery fee" value={fee} onChange={(e) => setFee(e.target.value)} />
          <button disabled={act.busy} onClick={confirm}>Confirm group</button>
          <h3>Or decline</h3>
          <Field label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button disabled={act.busy || !reason} onClick={decline}>Decline group</button>
          <ErrorText error={act.error} />
        </>) : null}
        {g.binding ? <><h3>Agreed terms</h3><pre>{JSON.stringify(costs.data ?? g.terms, null, 2)}</pre></> : null}
      </>) : null}
    </Page>
  );
}
