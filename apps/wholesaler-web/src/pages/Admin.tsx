import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorText, Page, Status, useAction, useLoad } from "../ui";

// Platform staff only. Everyone else gets a 403 from the server and sees the error below.
export function Admin() {
  const { data, error, loading, reload } = useLoad<any[]>("/admin/suppliers/pending/", true);
  const act = useAction();
  const decide = (id: string, verb: "verify" | "suspend") => {
    const note = prompt(`${verb} - note (internal, never shown to shops):`, "");
    if (note === null) return;
    act.run(async () => { await api(`/admin/suppliers/${id}/${verb}/`, { method: "POST", body: { note } }); reload(); });
  };
  return (
    <Page title="Supplier verification (platform staff)">
      <p><Link to="/">Back</Link></p>
      <Status loading={loading} error={error} /><ErrorText error={act.error} />
      <ul>{data?.map((w) => (
        <li key={w.id}>{w.business_name} - {w.location_text} - {w.contact_phone} - registered {new Date(w.created_at).toLocaleDateString()}{" "}
          <button onClick={() => decide(w.id, "verify")}>Verify</button> <button onClick={() => decide(w.id, "suspend")}>Suspend</button></li>))}</ul>
      {!loading && !error && data?.length === 0 ? <p>Nobody is waiting for verification.</p> : null}
    </Page>
  );
}
