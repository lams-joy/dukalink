import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorText, Page, Status, useAction, useLoad } from "../ui";

const FILTERS = ["open", "all", "received", "cancelled"];

export function Orders() {
  const { wid } = useParams();
  const [filter, setFilter] = useState("open");
  const qs = filter === "open" ? "?open=true" : filter === "all" ? "" : `?status=${filter}`;
  const { data, error, loading, reload } = useLoad<any[]>(`/wholesalers/${wid}/orders/${qs}`, true);
  const act = useAction();
  const post = (id: string, verb: string, body?: object) => act.run(async () => { await api(`/wholesalers/${wid}/orders/${id}/${verb}/`, { method: "POST", body: body ?? {} }); reload(); });
  const withReason = (id: string, verb: string, label: string) => { const reason = prompt(`${label} - reason:`); if (reason) post(id, verb, { reason }); };
  const confirm = (id: string) => { const fee = prompt("Delivery fee (KES, 0 if none):", "0"); if (fee !== null) post(id, "confirm", { delivery_fee: fee }); };

  return (
    <Page title="Orders">
      <p><Link to={`/w/${wid}`}>Back</Link> | {FILTERS.map((f) => <button key={f} disabled={f === filter} onClick={() => setFilter(f)}>{f}</button>)}</p>
      <Status loading={loading} error={error} /><ErrorText error={act.error} />
      {data?.map((o) => (
        <article key={o.id}>
          <h3>{o.shop.name} <span className={`pill ${o.status === "received" ? "good" : ["cancelled", "rejected"].includes(o.status) ? "bad" : "info"}`}>{o.status}</span>{o.group_order_id ? <span className="pill">group buy</span> : null}</h3>
          <p>Submitted {new Date(o.submitted_at).toLocaleString()} | {o.delivery_method}{o.delivery_address ? `: ${o.delivery_address}` : ""} | Contact {o.contact_phone || "-"}</p>
          <ul>{o.items.map((i: any) => <li key={i.id}>{i.quantity} x {i.product_name} ({i.unit_name}) at {i.unit_price} = {i.line_total}{i.shortage ? ` - SHORT ${i.shortage}` : ""}</li>)}</ul>
          <p>Total {o.currency} {o.total_amount} (delivery {o.delivery_fee}){o.note ? ` | Note: ${o.note}` : ""}</p>
          {o.status === "submitted" ? <><button onClick={() => confirm(o.id)}>Confirm</button> <button onClick={() => withReason(o.id, "reject", "Reject")}>Reject</button></> : null}
          {o.status === "confirmed" ? <><button onClick={() => post(o.id, "dispatch")}>Mark dispatched</button> <button onClick={() => withReason(o.id, "cancel", "Cancel")}>Cancel</button></> : null}
          {o.status === "dispatched" ? <button onClick={() => withReason(o.id, "cancel", "Cancel")}>Cancel</button> : null}
        </article>))}
      {!loading && data?.length === 0 ? <p>Nothing here.</p> : null}
    </Page>
  );
}
