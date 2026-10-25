import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { api } from "../api";
import { ErrorText, Field, Page, useAction } from "../ui";

function Brand({ sub }: { sub: string }) {
  return <div className="brand-hero"><span className="mark big">D</span><h1>DukaLink</h1><p>{sub}</p></div>;
}

export function Login() {
  const { user, signIn } = useAuth();
  const [phone, setPhone] = useState(""); const [pw, setPw] = useState("");
  const { busy, error, run } = useAction();
  if (user) return <Navigate to="/" replace />;
  return (
    <><Brand sub="Sell to shops across your region" />
    <Page title="Sign in">
      <form onSubmit={(e) => { e.preventDefault(); run(() => signIn(phone, pw)); }}>
        <Field label="Phone number" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <Field label="Password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <ErrorText error={error} />
        <button disabled={busy}>Sign in</button>
      </form>
      <p><Link to="/register">Create an account</Link></p>
    </Page></>
  );
}

export function Register() {
  const { signIn } = useAuth(); const nav = useNavigate();
  const [full_name, setName] = useState(""); const [phone_number, setPhone] = useState(""); const [password, setPw] = useState("");
  const { busy, error, run } = useAction();
  const submit = () => run(async () => {
    await api("/auth/register/", { method: "POST", auth: false, body: { phone_number, full_name, password } });
    await signIn(phone_number, password); nav("/");
  });
  return (
    <><Brand sub="Reach shops that order in bulk" />
    <Page title="Create your account">
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Field label="Full name" value={full_name} onChange={(e) => setName(e.target.value)} />
        <Field label="Phone number" value={phone_number} onChange={(e) => setPhone(e.target.value)} />
        <Field label="Password" type="password" value={password} onChange={(e) => setPw(e.target.value)} />
        <ErrorText error={error} />
        <button disabled={busy}>Register</button>
      </form>
      <p><Link to="/login">Back to sign in</Link></p>
    </Page></>
  );
}
