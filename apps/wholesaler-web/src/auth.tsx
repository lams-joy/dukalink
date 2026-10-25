import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearTokens, hasSession, onSignedOut, saveTokens } from "./api";

type User = { id: string; phone_number: string; full_name: string; is_staff: boolean };
type Ctx = { ready: boolean; user: User | null; signIn(p: string, pw: string): Promise<void>; signOut(): void };
const C = createContext<Ctx>(null as any);
export const useAuth = () => useContext(C);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    onSignedOut(() => setUser(null));
    (async () => { try { if (hasSession()) setUser(await api("/me/")); } catch {} setReady(true); })();
  }, []);
  const signIn = async (phone_number: string, password: string) => {
    const t = await api("/auth/login/", { method: "POST", auth: false, body: { phone_number, password } });
    saveTokens(t.access, t.refresh);
    setUser(await api("/me/"));
  };
  return <C.Provider value={{ ready, user, signIn, signOut: () => { clearTokens(); setUser(null); } }}>{children}</C.Provider>;
}
