import { Link, useParams } from "react-router-dom";
import { Page, Status, useLoad } from "../ui";
import { Icon } from "../icons";

export function Dashboard() {
  const { wid } = useParams();
  const w = useLoad<any>(`/wholesalers/${wid}/`);
  const open = useLoad<any[]>(`/wholesalers/${wid}/orders/?open=true`, true);
  const groups = useLoad<any[]>(`/wholesalers/${wid}/group-orders/?status=closed`, true);
  const offers = useLoad<any[]>(`/wholesalers/${wid}/offers/`, true);
  const b = w.data;
  const submitted = open.data?.filter((o) => o.status === "submitted").length ?? 0;
  return (
    <Page title={b?.business_name ?? "Business"}>
      <Status loading={w.loading} error={w.error} />
      {b ? <p><span className={`pill ${b.verification_status === "verified" ? "good" : "warn"}`}>{b.verification_status}</span> {b.location_text} {b.status_note ? `- ${b.status_note}` : ""}</p> : null}
      {b && b.verification_status !== "verified" ? <div className="banner">Shops cannot see your offers until the business is verified.</div> : null}
      <div className="stats">
        <Link to={`/w/${wid}/orders`} className="stat"><span className="stat-icon"><Icon name="truck" size={18} /></span><small>Open orders</small><strong>{open.data?.length ?? "-"}</strong>{submitted ? <em>{submitted} need confirming</em> : null}</Link>
        <Link to={`/w/${wid}/groups`} className="stat"><span className="stat-icon"><Icon name="users" size={18} /></span><small>Group buys awaiting you</small><strong>{groups.data?.length ?? "-"}</strong></Link>
        <Link to={`/w/${wid}/offers`} className="stat"><span className="stat-icon"><Icon name="tag" size={18} /></span><small>Live offers</small><strong>{offers.data?.filter((o) => o.is_active).length ?? "-"}</strong></Link>
      </div>
    </Page>
  );
}
