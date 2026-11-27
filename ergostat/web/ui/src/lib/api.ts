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

/* GETs of the same address under way at once are one request: a page of panels reading the same answer (an agent's
   sections, an item's) asks the server once. Each caller may still stop waiting (its signal); the request itself goes
   on while anyone still waits, and is cancelled once every caller has stopped (a query editor's preview, asked again
   as its text changes), then forgotten. A caller with no signal always waits. */
interface Asked { answer: Promise<unknown>; ctl: AbortController; waiting: number; kept: boolean }
const inFlight = new Map<string, Asked>();

export async function apiGet<T = any>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const url = apiUrl(path, params);
  if (signal?.aborted) throw new DOMException("aborted", "AbortError");
  let mine = inFlight.get(url);
  if (!mine) {
    const ctl = new AbortController();
    const one: Asked = { answer: Promise.resolve(), ctl, waiting: 0, kept: false };
    one.answer = (async () => {
      const r = await fetch(url, { signal: ctl.signal });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new ApiError(body.error || `${path}: ${r.status}`, r.status);
      }
      return r.json() as Promise<T>;
    })().finally(() => { if (inFlight.get(url) === one) inFlight.delete(url); });
    inFlight.set(url, one);
    mine = one;
  }
  const asked = mine;
  if (!signal) {
    asked.kept = true;
    return asked.answer as Promise<T>;
  }
  asked.waiting += 1;
  return new Promise<T>((resolve, reject) => {
    const stop = () => {
      reject(new DOMException("aborted", "AbortError"));
      asked.waiting -= 1;
      if (asked.waiting <= 0 && !asked.kept) {          // nobody waits for it any more: cancel it
        if (inFlight.get(url) === asked) inFlight.delete(url);
        asked.ctl.abort();
      }
    };
    signal.addEventListener("abort", stop, { once: true });
    (asked.answer as Promise<T>).then(resolve, reject).finally(() => signal.removeEventListener("abort", stop));
  });
}

/** A write whose arguments are in the query (the owner's answers, proposals). */
export async function apiPost<T = any>(path: string, params: Params = {}): Promise<T> {
  const r = await fetch(apiUrl(path, params), { method: "POST", headers: { "X-Ergostat-Token": token() } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(body.error || `${path}: ${r.status}`, r.status);
  return body;
}

/** A write whose body is JSON (a message to the work in flight, a dashboard saved). */
export async function apiSend<T = any>(path: string, body: unknown, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const r = await fetch(apiUrl(path, params), {
    method: "POST",
    signal,
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Ergostat-Token": token() },
  });
  const got = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(got.error || `${path}: ${r.status}`, r.status);
  return got;
}

export const isAbort = (e: unknown): boolean => (e as Error)?.name === "AbortError";
