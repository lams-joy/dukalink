import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorText, Field, Page, Status, useAction, useLoad } from "../ui";

export function Businesses() {
  const { data, error, loading } = useLoad<any[]>("/wholesalers/", true);
  return (
    <Page title="Your wholesale businesses">
      <Status loading={loading} error={error} />
      <ul>{data?.map((w) => (
        <li key={w.id}><Link to={`/w/${w.id}`}>{w.business_name}</Link> - {w.location_text} - {w.verification_status} ({w.my_role})</li>
      ))}</ul>
      {!loading && data?.length === 0 ? <p>No business yet.</p> : null}
      <p><Link to="/new">+ Register a business</Link></p>
    </Page>
  );
}

export function NewBusiness() {
  const nav = useNavigate();
  const [business_name, setName] = useState(""); const [contact_phone, setPhone] = useState(""); const [location_text, setLoc] = useState("");
  const { busy, error, run } = useAction();
  const save = () => run(async () => { const w = await api("/wholesalers/", { method: "POST", body: { business_name, contact_phone, location_text } }); nav(`/w/${w.id}`); });
  return (
    <Page title="Register a business">
      <p>New businesses are reviewed before shops can see your offers.</p>
      <form onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Business name" value={business_name} onChange={(e) => setName(e.target.value)} />
        <Field label="Business phone" value={contact_phone} onChange={(e) => setPhone(e.target.value)} />
        <Field label="Location" value={location_text} onChange={(e) => setLoc(e.target.value)} />
        <ErrorText error={error} />
        <button disabled={busy}>Save</button>
      </form>
    </Page>
  );
}
