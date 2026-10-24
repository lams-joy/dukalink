import { Link, useParams } from "react-router-dom";
import { Page, Status, useLoad } from "../ui";

export function Dashboard() {
  const { wid } = useParams();
  const w = useLoad<any>(`/wholesalers/${wid}/`);
  const open = useLoad<any[]>(`/wholesalers/${wid}/orders/?open=true`, true);
  const groups = useLoad<any[]>(`/wholesalers/${wid}/group-orders/?status=closed`, true);
  const b = w.data;
  return (
    <Page title={b?.business_name ?? "Business"}>
      <Status loading={w.loading} error={w.error} />
      {b ? <p>Status: {b.verification_status}{b.status_note ? ` - ${b.status_note}` : ""} | Your role: {b.my_role}</p> : null}
      {b && b.verification_status !== "verified" ? <p>Shops cannot see your offers until the business is verified.</p> : null}
      <ul>
        <li><Link to={`/w/${wid}/orders`}>Orders</Link> ({open.data?.length ?? "..."} open)</li>
        <li><Link to={`/w/${wid}/groups`}>Group buys</Link> ({groups.data?.length ?? "..."} waiting for your decision)</li>
        <li><Link to={`/w/${wid}/offers`}>Offers and prices</Link></li>
        <li><Link to={`/w/${wid}/settings`}>Business settings, team and activity log</Link></li>
      </ul>
      <p><Link to="/">All businesses</Link></p>
    </Page>
  );
}
