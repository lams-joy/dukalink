// Platform staff maintain the shared product catalogue here. The API enforces staff-only access.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { gradientFor, Icon } from "../icons";
import { ErrorText, Field, Page, Status, useAction, useLoad } from "../ui";

export function AdminCatalogue() {
  const [q, setQ] = useState(""); const [showOff, setShowOff] = useState(false);
  const { data, error, loading } = useLoad<any[]>(`/admin/catalog/products/?q=${encodeURIComponent(q)}${showOff ? "&include_inactive=true" : ""}`, true);
  return (
    <Page title="Product catalogue">
      <p className="muted">Products shops and wholesalers choose from. Shops cannot edit these.</p>
      <p><Link to="/admin/catalogue/new" className="cta"><Icon name="plus" /> New product</Link></p>
      <Field label="Search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="name, brand, category or barcode" />
      <label><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> Show retired products</label>
      <Status loading={loading} error={error} />
      <div className="grid">{data?.map((p) => (
        <Link key={p.id} to={`/admin/catalogue/${p.id}`} className="product">
          <div className="thumb" style={{ background: gradientFor(p.name) }}><span>{p.name.charAt(0)}</span></div>
          <h4>{p.name}</h4>
          <p className="muted">{p.category || "No category"} - counted in {p.base_unit}</p>
          <p>{p.units.filter((u: any) => u.is_active).length} units{!p.is_active ? <span className="pill bad">retired</span> : null}</p>
        </Link>))}</div>
      {!loading && data?.length === 0 ? <p>Nothing found. Load the starter list with <code>seed_catalog</code>, or add a product.</p> : null}
    </Page>
  );
}

type UnitRow = { unit_name: string; base_quantity: string };

export function NewAdminProduct() {
  const nav = useNavigate();
  const [name, setName] = useState(""); const [brand, setBrand] = useState(""); const [category, setCategory] = useState("");
  const [barcode, setBarcode] = useState(""); const [base, setBase] = useState("");
  const [units, setUnits] = useState<UnitRow[]>([]);
  const act = useAction();
  const setRow = (i: number, k: keyof UnitRow, v: string) => setUnits(units.map((u, j) => (j === i ? { ...u, [k]: v } : u)));
  const save = () => act.run(async () => {
    const p = await api("/admin/catalog/products/", { method: "POST", body: { name, brand, category, barcode, base_unit: base, units: units.filter((u) => u.unit_name && u.base_quantity) } });
    nav(`/admin/catalogue/${p.id}`);
  });
  return (
    <Page title="New catalogue product">
      <p><Link to="/admin/catalogue"><Icon name="arrow" /> Back to catalogue</Link></p>
      <form onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Field label="Brand (optional)" value={brand} onChange={(e) => setBrand(e.target.value)} />
        <Field label="Category" value={category} onChange={(e) => setCategory(e.target.value)} />
        <Field label="Barcode (optional)" value={barcode} onChange={(e) => setBarcode(e.target.value)} />
        <Field label="Base unit - the smallest thing stock is counted in (kg, litre, piece)" value={base} onChange={(e) => setBase(e.target.value)} />
        <h3>Other units</h3>
        <p className="muted">Write how many base units one of them holds, e.g. "50 kg sack" holds 50.</p>
        {units.map((u, i) => (
          <div key={i} className="row">
            <input placeholder="Unit name, e.g. 50 kg sack" value={u.unit_name} onChange={(e) => setRow(i, "unit_name", e.target.value)} />
            <input placeholder={`Holds how many ${base || "base units"}`} value={u.base_quantity} onChange={(e) => setRow(i, "base_quantity", e.target.value)} />
            <button type="button" className="ghost" onClick={() => setUnits(units.filter((_, j) => j !== i))}>Remove</button>
          </div>))}
        <button type="button" className="ghost" onClick={() => setUnits([...units, { unit_name: "", base_quantity: "" }])}>+ Add a unit</button>
        <ErrorText error={act.error} />
        <p><button disabled={act.busy || !name || !base}>Create product</button></p>
      </form>
    </Page>
  );
}

export function AdminProduct() {
  const { pid } = useParams();
  const { data: p, error, loading, reload } = useLoad<any>(`/admin/catalog/products/${pid}/`);
  const [edit, setEdit] = useState<any>(null);
  const [uName, setUName] = useState(""); const [uQty, setUQty] = useState("");
  const a = useAction(); const u = useAction(); const unit = useAction();
  const start = () => setEdit({ name: p.name, brand: p.brand, category: p.category, barcode: p.barcode });
  const saveProduct = () => a.run(async () => { await api(`/admin/catalog/products/${pid}/`, { method: "PATCH", body: edit }); setEdit(null); reload(); });
  const toggleActive = () => a.run(async () => { await api(`/admin/catalog/products/${pid}/`, { method: "PATCH", body: { is_active: !p.is_active } }); reload(); });
  const addUnit = () => u.run(async () => { await api(`/admin/catalog/products/${pid}/units/`, { method: "POST", body: { unit_name: uName, base_quantity: uQty } }); setUName(""); setUQty(""); reload(); });
  const patchUnit = (id: string, body: object) => unit.run(async () => { await api(`/admin/catalog/products/${pid}/units/${id}/`, { method: "PATCH", body }); reload(); });
  return (
    <Page title={p?.name ?? "Product"}>
      <p><Link to="/admin/catalogue"><Icon name="arrow" /> Back to catalogue</Link></p>
      <Status loading={loading} error={error} />
      {p ? (<>
        <p>{p.brand ? `${p.brand} - ` : ""}{p.category || "No category"} - counted in <strong>{p.base_unit}</strong> {!p.is_active ? <span className="pill bad">retired</span> : <span className="pill good">live</span>}</p>
        {edit ? (
          <form onSubmit={(e) => { e.preventDefault(); saveProduct(); }}>
            <Field label="Name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
            <Field label="Brand" value={edit.brand} onChange={(e) => setEdit({ ...edit, brand: e.target.value })} />
            <Field label="Category" value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} />
            <Field label="Barcode" value={edit.barcode} onChange={(e) => setEdit({ ...edit, barcode: e.target.value })} />
            <ErrorText error={a.error} />
            <button disabled={a.busy}>Save</button><button type="button" className="ghost" onClick={() => setEdit(null)}>Cancel</button>
          </form>
        ) : (<>
          <button type="button" className="ghost" onClick={start}>Edit details</button>
          <button type="button" className="ghost" disabled={a.busy} onClick={toggleActive}>{p.is_active ? "Retire product" : "Bring back"}</button>
          <ErrorText error={a.error} />
        </>)}
        <h3>Units</h3>
        <p className="muted">The base unit cannot be changed, and a unit's size cannot be edited. If a size is wrong, retire the unit and add a new one.</p>
        <table><thead><tr><th>Unit</th><th>Holds</th><th>Buy</th><th>Sell</th><th>Status</th><th></th></tr></thead>
          <tbody>{p.units.map((x: any) => (
            <tr key={x.id}>
              <td>{x.unit_name}</td><td>{Number(x.base_quantity)} {p.base_unit}</td>
              <td><input type="checkbox" checked={x.is_purchase_unit} onChange={(e) => patchUnit(x.id, { is_purchase_unit: e.target.checked })} /></td>
              <td><input type="checkbox" checked={x.is_sale_unit} onChange={(e) => patchUnit(x.id, { is_sale_unit: e.target.checked })} /></td>
              <td>{x.is_active ? <span className="pill good">live</span> : <span className="pill bad">retired</span>}</td>
              <td>{x.unit_name !== p.base_unit ? <button type="button" className="ghost" onClick={() => patchUnit(x.id, { is_active: !x.is_active })}>{x.is_active ? "Retire" : "Restore"}</button> : <span className="muted">base unit</span>}</td>
            </tr>))}</tbody></table>
        <ErrorText error={unit.error} />
        <h3>Add a unit</h3>
        <form className="row" onSubmit={(e) => { e.preventDefault(); addUnit(); }}>
          <input placeholder="Unit name, e.g. 24 x 2 kg carton" value={uName} onChange={(e) => setUName(e.target.value)} />
          <input placeholder={`Holds how many ${p.base_unit}`} value={uQty} onChange={(e) => setUQty(e.target.value)} />
          <button disabled={u.busy || !uName || !uQty}>Add</button>
        </form>
        <ErrorText error={u.error} />
      </>) : null}
    </Page>
  );
}
