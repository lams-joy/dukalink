import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, apiList } from "../api";
import { gradientFor, Icon } from "../icons";
import { ErrorText, Field, Page, Status, useAction, useLoad } from "../ui";

const AVAIL = ["in_stock", "limited", "out_of_stock"];

export function Offers() {
  const { wid } = useParams();
  const { data, error, loading } = useLoad<any[]>(`/wholesalers/${wid}/offers/`, true);
  return (
    <Page title="Offers and prices">
      <p> <Link to={`/w/${wid}/offers/new`} className="cta"><Icon name="plus" /> New offer</Link></p>
      <Status loading={loading} error={error} />
      <div className="grid">{data?.map((o) => (
        <Link key={o.id} to={`/w/${wid}/offers/${o.id}`} className="product">
          <div className="thumb" style={{ background: gradientFor(o.product.name) }}><span>{o.product.name.charAt(0)}</span></div>
          <h4>{o.product.name}</h4>
          <p className="muted">per {o.unit.unit_name} - min {o.minimum_order_quantity}</p>
          <p className="price">{o.currency} {Number(o.price_per_unit).toLocaleString()}</p>
          <p><span className={`pill ${o.availability === "in_stock" ? "good" : o.availability === "limited" ? "warn" : "bad"}`}>{o.availability.replace("_", " ")}</span>{!o.is_active ? <span className="pill">hidden</span> : null}{o.tiers?.length ? <span className="pill info">{o.tiers.length} bulk tiers</span> : null}</p>
        </Link>))}</div>
      {!loading && data?.length === 0 ? <p>No offers yet.</p> : null}
    </Page>
  );
}

export function NewOffer() {
  const { wid } = useParams(); const nav = useNavigate();
  const [q, setQ] = useState(""); const [results, setResults] = useState<any[]>([]); const [product, setProduct] = useState<any>(null);
  const [unitId, setUnitId] = useState(""); const [price, setPrice] = useState(""); const [min, setMin] = useState("1");
  const [availability, setAvail] = useState("in_stock"); const [areas, setAreas] = useState("");
  const search = useAction(); const save = useAction();
  const find = () => search.run(async () => setResults(await apiList(`/catalog/products/?q=${encodeURIComponent(q)}`)));
  const create = () => save.run(async () => {
    const o = await api(`/wholesalers/${wid}/offers/`, { method: "POST", body: {
      product_id: product.id, product_unit_id: unitId, price_per_unit: price, minimum_order_quantity: min, availability, delivery_areas: areas } });
    nav(`/w/${wid}/offers/${o.id}`);
  });
  return (
    <Page title="New offer">
      <p><Link to={`/w/${wid}/offers`}>Back</Link></p>
      {!product ? (<>
        <form onSubmit={(e) => { e.preventDefault(); find(); }}>
          <Field label="Search the catalogue" value={q} onChange={(e) => setQ(e.target.value)} /><button>Search</button>
        </form>
        <ErrorText error={search.error} />
        <ul>{results.map((p) => <li key={p.id}><button onClick={() => { setProduct(p); setUnitId(p.units.find((u: any) => u.is_purchase_unit)?.id ?? p.units[0]?.id ?? ""); }}>{p.name}{p.brand ? ` - ${p.brand}` : ""}</button></li>)}</ul>
      </>) : (
        <form onSubmit={(e) => { e.preventDefault(); create(); }}>
          <p>{product.name} (base unit {product.base_unit}) <button type="button" onClick={() => setProduct(null)}>Change</button></p>
          <label>Sold per <select value={unitId} onChange={(e) => setUnitId(e.target.value)}>
            {product.units.map((u: any) => <option key={u.id} value={u.id}>{u.unit_name} (= {u.base_quantity} {product.base_unit})</option>)}</select></label>
          <Field label="Price per unit (KES)" value={price} onChange={(e) => setPrice(e.target.value)} />
          <Field label="Minimum order (units)" value={min} onChange={(e) => setMin(e.target.value)} />
          <label>Availability <select value={availability} onChange={(e) => setAvail(e.target.value)}>{AVAIL.map((a) => <option key={a}>{a}</option>)}</select></label>
          <Field label="Delivery areas" value={areas} onChange={(e) => setAreas(e.target.value)} />
          <ErrorText error={save.error} /><button disabled={save.busy}>Create offer</button>
        </form>
      )}
    </Page>
  );
}

export function EditOffer() {
  const { wid, oid } = useParams();
  const { data: o, error, loading, reload } = useLoad<any>(`/wholesalers/${wid}/offers/${oid}/`);
  const [price, setPrice] = useState(""); const [avail, setAvail] = useState("in_stock"); const [active, setActive] = useState(true);
  const [tiers, setTiers] = useState<{ minimum_quantity: string; unit_price: string }[]>([]);
  const a = useAction(); const t = useAction();
  useEffect(() => { if (o) { setPrice(o.price_per_unit); setAvail(o.availability); setActive(o.is_active);
    setTiers(o.tiers.map((x: any) => ({ minimum_quantity: x.minimum_quantity, unit_price: x.unit_price }))); } }, [o]);
  const save = () => a.run(async () => { await api(`/wholesalers/${wid}/offers/${oid}/`, { method: "PATCH", body: { price_per_unit: price, availability: avail, is_active: active } }); reload(); });
  const saveTiers = () => t.run(async () => { await api(`/wholesalers/${wid}/offers/${oid}/tiers/`, { method: "PUT", body: { tiers } }); reload(); });
  const setTier = (i: number, k: "minimum_quantity" | "unit_price", v: string) => setTiers(tiers.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  return (
    <Page title={o ? `${o.product.name} per ${o.unit.unit_name}` : "Offer"}>
      <p><Link to={`/w/${wid}/offers`}>Back</Link></p>
      <Status loading={loading} error={error} />
      {o ? (<>
        <form onSubmit={(e) => { e.preventDefault(); save(); }}>
          <Field label="Price per unit (KES)" value={price} onChange={(e) => setPrice(e.target.value)} />
          <label>Availability <select value={avail} onChange={(e) => setAvail(e.target.value)}>{AVAIL.map((x) => <option key={x}>{x}</option>)}</select></label>
          <label><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Visible to shops</label>
          <ErrorText error={a.error} /><button disabled={a.busy}>Save</button>
        </form>
        <h3>Volume prices</h3>
        {tiers.map((x, i) => (
          <div key={i}>
            <input placeholder="from quantity" value={x.minimum_quantity} onChange={(e) => setTier(i, "minimum_quantity", e.target.value)} />
            <input placeholder="unit price" value={x.unit_price} onChange={(e) => setTier(i, "unit_price", e.target.value)} />
            <button onClick={() => setTiers(tiers.filter((_, j) => j !== i))}>Remove</button>
          </div>))}
        <button onClick={() => setTiers([...tiers, { minimum_quantity: "", unit_price: "" }])}>+ Add tier</button>
        <ErrorText error={t.error} /><button disabled={t.busy} onClick={saveTiers}>Save tiers</button>
      </>) : null}
    </Page>
  );
}
