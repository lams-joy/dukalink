// Unstyled helpers. Restyle here first, then per page.
import { useCallback, useEffect, useState, type ReactNode, type InputHTMLAttributes } from "react";
import { api, apiList, errorText } from "./api";

export const Field = ({ label, ...p }: { label: string } & InputHTMLAttributes<HTMLInputElement>) => (
  <div><label>{label} <input {...p} /></label></div>
);
export const ErrorText = ({ error }: { error?: string | null }) => (error ? <p role="alert">Error: {error}</p> : null);

export function useLoad<T = any>(path: string | null, list = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true); setError(null);
    try { setData((list ? await apiList(path) : await api(path)) as T); } catch (e) { setError(errorText(e)); }
    setLoading(false);
  }, [path, list]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload };
}
export const Status = ({ loading, error }: { loading: boolean; error: string | null }) =>
  loading ? <p>Loading...</p> : <ErrorText error={error} />;

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return { busy, error, run };
}
export const Page = ({ title, children }: { title: string; children: ReactNode }) => (<section><h2>{title}</h2>{children}</section>);
