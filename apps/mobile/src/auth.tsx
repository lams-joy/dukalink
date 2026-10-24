import React, { createContext, useContext, useEffect, useState } from "react";
import { api, clearTokens, loadTokens, saveTokens, setSignedOutHandler } from "./api";

type User = { id: string; phone_number: string; full_name: string };
type Ctx = { ready: boolean; user: User | null; signIn(phone: string, password: string): Promise<void>; signOut(): Promise<void> };
const AuthCtx = createContext<Ctx>(null as any);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    setSignedOutHandler(() => setUser(null));
    (async () => {
      try { if (await loadTokens()) setUser(await api<User>("/me/")); } catch {}
      setReady(true);
    })();
  }, []);

  const signIn = async (phone_number: string, password: string) => {
    const t = await api<{ access: string; refresh: string }>("/auth/login/", { method: "POST", body: { phone_number, password }, auth: false });
    await saveTokens(t.access, t.refresh);
    setUser(await api<User>("/me/"));
  };
  const signOut = async () => { await clearTokens(); setUser(null); };

  return <AuthCtx.Provider value={{ ready, user, signIn, signOut }}>{children}</AuthCtx.Provider>;
}
