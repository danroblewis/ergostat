/* The server's API: every read is GET /api/PATH?since=&at=&..., every write a POST carrying the page's token (the
   server writes it into the page it serves, <meta name="ergostat-token">). */

export type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export const token = (): string =>
  document.querySelector<HTMLMetaElement>('meta[name="ergostat-token"]')?.content || "";
/** The page is served public and read only (web: open: read): no writes. */
export const isPublic = (): boolean => !!document.querySelector('meta[name="ergostat-public"]');

export function query(params: Params): URLSearchParams {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === false) continue;
    for (const x of ([] as unknown[]).concat(v)) q.append(k, String(x));
  }
  return q;
}

export function apiUrl(path: string, params: Params = {}): string {
  const q = query(params).toString();
  return `/api/${path}${q ? `?${q}` : ""}`;
}

export async function apiGet<T = any>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const r = await fetch(apiUrl(path, params), { signal });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new ApiError(body.error || `${path}: ${r.status}`, r.status);
  }
  return r.json();
}

/** A write whose arguments are in the query (the owner's answers, proposals). */
export async function apiPost<T = any>(path: string, params: Params = {}): Promise<T> {
  const r = await fetch(apiUrl(path, params), { method: "POST", headers: { "X-Ergostat-Token": token() } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(body.error || `${path}: ${r.status}`, r.status);
  return body;
}

/** A write whose body is JSON (a message to the work in flight, a dashboard saved). */
export async function apiSend<T = any>(path: string, body: unknown, params: Params = {}): Promise<T> {
  const r = await fetch(apiUrl(path, params), {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Ergostat-Token": token() },
  });
  const got = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(got.error || `${path}: ${r.status}`, r.status);
  return got;
}

export const isAbort = (e: unknown): boolean => (e as Error)?.name === "AbortError";
