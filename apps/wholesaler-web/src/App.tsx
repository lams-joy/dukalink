import { Link, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Login, Register } from "./pages/Auth";
import { Businesses, NewBusiness } from "./pages/Businesses";
import { Dashboard } from "./pages/Dashboard";
import { Offers, NewOffer, EditOffer } from "./pages/Offers";
import { Orders } from "./pages/Orders";
import { Groups, GroupDetail } from "./pages/Groups";
import { Settings } from "./pages/Settings";
import { Admin } from "./pages/Admin";

function Protected() {
  const { ready, user, signOut } = useAuth();
  if (!ready) return <p>Loading...</p>;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <>
      <header>
        <Link to="/">DukaLink Wholesaler</Link> | {user.full_name} | <Link to="/admin">Admin</Link> <button onClick={signOut}>Sign out</button>
      </header>
      <main><Outlet /></main>
    </>
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
        <Route path="w/:wid" element={<Dashboard />} />
        <Route path="w/:wid/offers" element={<Offers />} />
        <Route path="w/:wid/offers/new" element={<NewOffer />} />
        <Route path="w/:wid/offers/:oid" element={<EditOffer />} />
        <Route path="w/:wid/orders" element={<Orders />} />
        <Route path="w/:wid/settings" element={<Settings />} />
        <Route path="admin" element={<Admin />} />
        <Route path="w/:wid/groups" element={<Groups />} />
        <Route path="w/:wid/groups/:gid" element={<GroupDetail />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
