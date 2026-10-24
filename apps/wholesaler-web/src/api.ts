// Same contract as the mobile client: bearer token, one silent refresh, error envelope, pagination.
const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) { super(message); }
}
let signedOut: () => void = () => {};
export const onSignedOut = (fn: () => void) => (signedOut = fn);
export const hasSession = () => !!localStorage.getItem("refresh");
export function saveTokens(access: string, refresh?: string) {
  localStorage.setItem("access", access);
  if (refresh) localStorage.setItem("refresh", refresh);
}
export function clearTokens() { localStorage.removeItem("access"); localStorage.removeItem("refresh"); }

async function tryRefresh() {
  const refresh = localStorage.getItem("refresh");
  if (!refresh) return false;
  const res = await fetch(`${API_URL}/auth/refresh/`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh }) });
  if (!res.ok) return false;
  const d = await res.json(); saveTokens(d.access, d.refresh); return true;
}

export async function api<T = any>(path: string, o: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const { method = "GET", body, auth = true } = o;
  const send = () => fetch(`${API_URL}${path}`, {
    method,
    headers: { ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...(auth && localStorage.getItem("access") ? { Authorization: `Bearer ${localStorage.getItem("access")}` } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let res: Response;
  try { res = await send(); } catch { throw new ApiError(0, "network", `Cannot reach the server at ${API_URL}`); }
  if (res.status === 401 && auth && (await tryRefresh())) res = await send();
  if (res.status === 401 && auth) { clearTokens(); signedOut(); }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) { const e = data?.error; throw new ApiError(res.status, e?.code ?? "error", e?.message ?? `Request failed (${res.status})`, e?.details); }
  return data as T;
}
export async function apiList<T = any>(path: string): Promise<T[]> {
  const d = await api<any>(path);
  return Array.isArray(d) ? d : d.results ?? [];
}
export const errorText = (e: unknown) => e instanceof ApiError ? `${e.message}${e.details ? " " + JSON.stringify(e.details) : ""}` : String(e);
