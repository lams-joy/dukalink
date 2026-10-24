// Offline queue. Online: write straight to the normal endpoint. If the network is down the
// operation is stored on the device and replayed through POST /shops/{id}/sync/ later.
// operation_id doubles as the idempotency key, so a replay can never double-apply.
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api, ApiError, uuid } from "./api";

export type QueuedOp = {
  operation_id: string; operation_type: string; payload: any; shopId: string;
  created_at: string; state: "pending" | "failed"; error?: string;
};
const KEY = "dukalink.queue";
const REST: Record<string, string> = { sale: "sales", purchase_receipt: "purchase-receipts", stock_adjustment: "stock-adjustments" };

export async function loadQueue(): Promise<QueuedOp[]> {
  try { return JSON.parse((await AsyncStorage.getItem(KEY)) ?? "[]"); } catch { return []; }
}
const saveQueue = (q: QueuedOp[]) => AsyncStorage.setItem(KEY, JSON.stringify(q));
export async function queueFor(shopId: string) { return (await loadQueue()).filter((o) => o.shopId === shopId); }

/** Returns {queued:true} when saved offline; throws ApiError for real server rejections. */
export async function sendOp(shopId: string, type: keyof typeof REST, payload: object): Promise<{ queued: boolean }> {
  const operation_id = uuid();
  try {
    await api(`/shops/${shopId}/${REST[type]}/`, { method: "POST", body: { idempotency_key: operation_id, ...payload } });
    return { queued: false };
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 0) throw e;
    const q = await loadQueue();
    q.push({ operation_id, operation_type: type, payload, shopId, created_at: new Date().toISOString(), state: "pending" });
    await saveQueue(q);
    return { queued: true };
  }
}

/** Replay pending operations for a shop. Returns counts; stops quietly if still offline. */
export async function flush(shopId: string): Promise<{ sent: number; failed: number; offline: boolean }> {
  const all = await loadQueue();
  const mine = all.filter((o) => o.shopId === shopId && o.state === "pending").slice(0, 100);
  if (mine.length === 0) return { sent: 0, failed: 0, offline: false };
  try {
    const res = await api<{ results: any[] }>(`/shops/${shopId}/sync/`, {
      method: "POST",
      body: { operations: mine.map(({ operation_id, operation_type, payload }) => ({ operation_id, operation_type, payload })) },
    });
    let sent = 0, failed = 0;
    const byId = new Map(res.results.map((r) => [r.operation_id, r]));
    const next = all.flatMap((o) => {
      const r = byId.get(o.operation_id);
      if (!r) return [o];
      if (r.status === "accepted" || r.status === "duplicate") { sent++; return []; }
      failed++;
      return [{ ...o, state: "failed" as const, error: `${r.status}: ${r.error?.message ?? ""} ${r.error?.details ? JSON.stringify(r.error.details) : ""}` }];
    });
    await saveQueue(next);
    return { sent, failed, offline: false };
  } catch (e) {
    if (e instanceof ApiError && e.status === 0) return { sent: 0, failed: 0, offline: true };
    throw e;
  }
}
export async function discard(operation_id: string) { await saveQueue((await loadQueue()).filter((o) => o.operation_id !== operation_id)); }
