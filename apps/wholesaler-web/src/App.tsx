import { Link, NavLink, Navigate, Outlet, Route, Routes, useParams } from "react-router-dom";
import { useAuth } from "./auth";
import { Icon, type IconName } from "./icons";
import { Login, Register } from "./pages/Auth";
import { Businesses, NewBusiness } from "./pages/Businesses";
import { Dashboard } from "./pages/Dashboard";
import { Offers, NewOffer, EditOffer } from "./pages/Offers";
import { Orders } from "./pages/Orders";
import { Groups, GroupDetail } from "./pages/Groups";
import { Settings } from "./pages/Settings";
import { Admin } from "./pages/Admin";
import { AdminCatalogue, AdminProduct, NewAdminProduct } from "./pages/AdminCatalogue";

function Protected() {
  const { ready, user, signOut } = useAuth();
  if (!ready) return <p>Loading...</p>;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <>
      <header>
        <Link to="/" className="brand"><span className="mark">D</span> DukaLink <em>Wholesale</em></Link>
        {user.is_staff ? <Link to="/admin" className="hbtn"><Icon name="shield" /> Platform admin</Link> : null}
        <span className="chip">{user.full_name}</span>
        <button className="icon-btn" onClick={signOut} aria-label="Sign out" title="Sign out"><Icon name="logout" /></button>
      </header>
      <main><Outlet /></main>
    </>
  );
}

function AdminLayout() {
  const { user } = useAuth();
  if (!user?.is_staff) return <Navigate to="/" replace />;   // non-staff never see admin pages
  return (
    <div className="shell">
      <nav className="sidebar">
        <NavLink to="/admin" end className={({ isActive }) => (isActive ? "active" : "")}><Icon name="shield" /> Verify wholesalers</NavLink>
        <NavLink to="/admin/catalogue" className={({ isActive }) => (isActive ? "active" : "")}><Icon name="package" /> Product catalogue</NavLink>
        <Link to="/" className="switch"><Icon name="repeat" /> Back to my businesses</Link>
      </nav>
      <div className="content"><Outlet /></div>
    </div>
  );
}

function BusinessLayout() {
  const { wid } = useParams();
  const item = (to: string, icon: IconName, label: string, end = false) => (
    <NavLink to={`/w/${wid}${to}`} end={end} className={({ isActive }) => (isActive ? "active" : "")}><Icon name={icon} /> {label}</NavLink>
  );
  return (
    <div className="shell">
      <nav className="sidebar">
        {item("", "grid", "Dashboard", true)}
        {item("/orders", "truck", "Orders")}
        {item("/offers", "tag", "Offers and prices")}
        {item("/groups", "users", "Group buys")}
        {item("/settings", "sliders", "Settings and team")}
        <Link to="/" className="switch"><Icon name="repeat" /> Switch business</Link>
      </nav>
      <div className="content"><Outlet /></div>
    </div>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<Protected />}>
        <Route index element={<Businesses />} />
        <Route path="new" element={<NewBusiness />} />
        <Route path="admin" element={<AdminLayout />}>
          <Route index element={<Admin />} />
          <Route path="catalogue" element={<AdminCatalogue />} />
          <Route path="catalogue/new" element={<NewAdminProduct />} />
          <Route path="catalogue/:pid" element={<AdminProduct />} />
        </Route>
        <Route path="w/:wid" element={<BusinessLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="offers" element={<Offers />} />
          <Route path="offers/new" element={<NewOffer />} />
          <Route path="offers/:oid" element={<EditOffer />} />
          <Route path="orders" element={<Orders />} />
          <Route path="settings" element={<Settings />} />
          <Route path="groups" element={<Groups />} />
          <Route path="groups/:gid" element={<GroupDetail />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
