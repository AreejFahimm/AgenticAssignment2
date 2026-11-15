// Typed client over the schema generated from FastAPI's OpenAPI (src/lib/api/schema.d.ts is GENERATED: do not hand-edit).
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

export function getToken(): string | null {
  try { return localStorage.getItem("gigbid_token"); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem("gigbid_token", t) : localStorage.removeItem("gigbid_token"); } catch { /* storage unavailable */ }
}

export const api = createClient<paths>({
  baseUrl: API_BASE,
  fetch: (req: Request) => {
    const h = new Headers(req.headers);
    const tok = getToken();
    if (tok) h.set("Authorization", `Bearer ${tok}`);
    h.set("x-trace-id", crypto.randomUUID().slice(0, 12)); // one trace id from the UI request onward
    return fetch(new Request(req, { headers: h }));
  },
});

/** Untyped helper for endpoints whose response model is free-form (job detail, approval payloads...). */
export async function getJson<T = any>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path, { headers: authHeaders() });
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.json();
}
export async function sendJson<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(API_BASE + path, { method, headers: { ...authHeaders(), "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.status === 204 ? (undefined as T) : r.json();
}
export function authHeaders(): Record<string, string> {
  const tok = getToken();
  return tok ? { Authorization: `Bearer ${tok}` } : {};
}
