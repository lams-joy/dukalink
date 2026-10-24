// Typed-ish API client. Handles the bearer token, one silent refresh on 401, and the
// {"error": {code, message, details}} envelope from the backend.
import { API_URL } from "./config";
import { getItem, setItem, removeItem } from "./storage";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

let access: string | null = null;
let refresh: string | null = null;
let onSignedOut: () => void = () => {};
export const setSignedOutHandler = (fn: () => void) => (onSignedOut = fn);

export async function loadTokens() {
  access = await getItem("access");
  refresh = await getItem("refresh");
  return !!refresh;
}
export async function saveTokens(a: string, r?: string) {
  access = a;
  await setItem("access", a);
  if (r) { refresh = r; await setItem("refresh", r); }
}
export async function clearTokens() {
  access = refresh = null;
  await removeItem("access");
  await removeItem("refresh");
}

async function tryRefresh(): Promise<boolean> {
  if (!refresh) return false;
  const res = await fetch(`${API_URL}/auth/refresh/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh }),
  });
  if (!res.ok) return false;
  const data = await res.json();
  await saveTokens(data.access, data.refresh);
  return true;
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const { method = "GET", body, auth = true } = opts;
  const send = () =>
    fetch(`${API_URL}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(auth && access ? { Authorization: `Bearer ${access}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  let res: Response;
  try { res = await send(); } catch { throw new ApiError(0, "network", `Cannot reach the server at ${API_URL}`); }
  if (res.status === 401 && auth && (await tryRefresh())) res = await send();
  if (res.status === 401 && auth) { await clearTokens(); onSignedOut(); }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(res.status, e?.code ?? "error", e?.message ?? data?.detail ?? `Request failed (${res.status})`, e?.details);
  }
  return data as T;
}

// Lists are paginated: {count, next, previous, results}. Unwrap to an array.
export async function apiList<T = any>(path: string): Promise<T[]> {
  const data = await api<any>(path);
  return Array.isArray(data) ? data : data.results ?? [];
}

export function uuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.details ? ` ${JSON.stringify(e.details)}` : "";
    return `${e.message}${d}`;
  }
  return String(e);
}
