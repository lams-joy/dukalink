import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorText, Field, Page, Status, useAction, useLoad } from "../ui";

export function Settings() {
  const { wid } = useParams();
  const { data: w, error, loading, reload } = useLoad<any>(`/wholesalers/${wid}/`);
  const audit = useLoad<any[]>(`/wholesalers/${wid}/audit-events/`, true);
  const [name, setName] = useState(""); const [phone, setPhone] = useState(""); const [loc, setLoc] = useState("");
  const [mPhone, setMPhone] = useState(""); const [role, setRole] = useState("staff"); const [added, setAdded] = useState<string | null>(null);
  const save = useAction(); const add = useAction();
  useEffect(() => { if (w) { setName(w.business_name); setPhone(w.contact_phone); setLoc(w.location_text); } }, [w]);
  const saveBiz = () => save.run(async () => { await api(`/wholesalers/${wid}/`, { method: "PATCH", body: { business_name: name, contact_phone: phone, location_text: loc } }); reload(); });
  const addMember = () => add.run(async () => { await api(`/wholesalers/${wid}/members/`, { method: "POST", body: { phone_number: mPhone, role } }); setAdded(`Added ${mPhone} as ${role}.`); setMPhone(""); audit.reload(); });
  return (
    <Page title="Business settings and team">
      <p><Link to={`/w/${wid}`}>Back</Link></p>
      <Status loading={loading} error={error} />
      {w ? (<>
        <p>Verification: {w.verification_status}{w.status_note ? ` - ${w.status_note}` : ""}</p>
        <form onSubmit={(e) => { e.preventDefault(); saveBiz(); }}>
          <Field label="Business name" value={name} onChange={(e) => setName(e.target.value)} />
          <Field label="Business phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          <Field label="Location" value={loc} onChange={(e) => setLoc(e.target.value)} />
          <ErrorText error={save.error} /><button disabled={save.busy}>Save</button>
        </form>
        <h3>Add a team member</h3>
        <p>They must already have a DukaLink account.</p>
        <form onSubmit={(e) => { e.preventDefault(); addMember(); }}>
          <Field label="Their phone number" value={mPhone} onChange={(e) => setMPhone(e.target.value)} />
          <label>Role <select value={role} onChange={(e) => setRole(e.target.value)}><option>staff</option><option>manager</option></select></label>
          <ErrorText error={add.error} />{added ? <p>{added}</p> : null}
          <button disabled={add.busy || !mPhone}>Add member</button>
        </form>
      </>) : null}
      <h3>Activity log</h3>
      <Status loading={audit.loading} error={audit.error} />
      <ul>{audit.data?.map((a) => <li key={a.id}>{new Date(a.created_at).toLocaleString()} - {a.action} {a.object_type}</li>)}</ul>
    </Page>
  );
}
