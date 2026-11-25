/* How numbers, times, durations, rates and costs are written: one formatter for each, as the old page's util.js. */

const MINUS = "−";
export const DASH = "–";

/** Integers as they are (thousands separated from 10,000), others to three significant figures, a real minus. */
export function fmt(x: unknown): string {
  if (x == null) return "?";
  if (typeof x !== "number") return String(x);
  if (!Number.isFinite(x)) return String(x);
  let n = x;
  if (Math.abs(n) < 1e-9) n = 0;
  let t: string;
  if (Number.isInteger(n)) t = Math.abs(n) >= 10000 ? n.toLocaleString("en-US") : String(n);
  else if (Math.abs(n) >= 100) {
    const r = Math.round(n);
    t = Math.abs(r) >= 10000 ? r.toLocaleString("en-US") : String(r);
  } else t = String(+n.toPrecision(3));
  return t.replace(/^-/, MINUS);
}

/** A share as a percentage: one that is not zero is never written "0%". */
export const shareText = (x: number | null | undefined): string =>
  x != null && x > 0 && x < 0.005 ? "<1%" : `${Math.round((x || 0) * 100)}%`;

/** Seconds, said shortly. */
export function dur(x: number | null | undefined): string {
  if (x == null) return "?";
  if (x < 60) return `${Math.max(1, Math.round(x))}s`;
  if (x < 3600) return `${Math.round(x / 60)}m`;
  if (x < 86400) return `${(x / 3600).toFixed(x < 36000 ? 1 : 0)}h`;
  return `${Math.round(x / 86400)}d`;
}

export const nowS = (): number => Date.now() / 1000;

export function ago(t: number | null | undefined, now: number = nowS()): string {
  if (!t) return "never";
  const d = now - t;
  if (d < 60) return `${Math.max(0, Math.round(d))}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

const ZONE = new Intl.DateTimeFormat("en-US", { timeZoneName: "short" });
/** "2026-11-22 04:03:55 PST", in the browser's zone. */
export function stamp(t: number | null | undefined): string {
  if (t == null || !Number.isFinite(+t)) return DASH;
  const d = new Date(t * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  const zone = ZONE.formatToParts(d).find((x) => x.type === "timeZoneName")?.value || "UTC";
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())} ${zone}`;
}
export const clock = (t: number): string =>
  new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });

const TIME_FIELD = /(^|_)at$|^(raised|since|started)$/;
/** A field that holds a time (*_at, raised, since, started), as a stamp; else null. */
export function timeField(name: string, v: unknown): string | null {
  if (!TIME_FIELD.test(String(name))) return null;
  const t = typeof v === "number" ? v : typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v) ? Date.parse(v) / 1000 : NaN;
  return Number.isFinite(t) && t > 1e8 && t < 1e11 ? stamp(t) : null;
}

export const usd = (x: number | null | undefined): string =>
  x == null ? DASH : x === 0 ? "$0" : x < 0.01 ? `$${x.toFixed(4)}` : x < 100 ? `$${x.toFixed(2)}` : `$${Math.round(x).toLocaleString("en-US")}`;
export const tokensText = (n: number | null | undefined): string =>
  n == null ? DASH : n === 0 ? "0" : n >= 1e6 ? `${+(n / 1e6).toPrecision(3)}M` : n >= 1e4 ? `${+(n / 1e3).toPrecision(3)}k` : String(n);
export const cpuText = (x: number | null | undefined): string => (x == null ? DASH : x < 60 ? `${+x.toPrecision(2)}s` : dur(x));
export const bytesText = (b: number | null | undefined): string =>
  b == null ? DASH : b >= 1e9 ? `${+(b / 1e9).toPrecision(3)} GB` : `${+(b / 1e6).toPrecision(3)} MB`;

/** Runs' cost with why it is none (util.js costText). */
export function costText(u: any, a?: any): string {
  const ai = a && (a.ai ?? [1, 2, 3].includes(a.rung));
  const back = !u.failed && /^workspace pool .* has none free for /.test(u.note || "");
  const unknown = u.unknown ?? (u.cost_usd == null && !back && (u.failed || u.note || u.exit !== 0) ? 1 : 0);
  if (u.cost_usd) return usd(u.cost_usd) + (ai && unknown ? ` + not known: ${unknown} failed or stopped` : "");
  if (u.tokens) return u.cost_usd == null ? "not priced" : "$0 reported";
  if (!u.runs) return a && !a.runs_itself ? (a.kind === "person" ? "a person, not priced" : "not run here") : "no runs, $0";
  if (ai && unknown) return `not known: ${unknown} failed or stopped`;
  return ai ? "free stand-in, $0" : "no AI, $0";
}

/* rates: every rate is kept per hour; shown per minute, hour or day as reads best (or the flow's own rate-unit) */
export type RateUnit = "minute" | "hour" | "day" | "week";
export const RATE_PER_HOUR: Record<RateUnit, number> = { minute: 1 / 60, hour: 1, day: 24, week: 168 };
export const RATE_SUFFIX: Record<RateUnit, string> = { minute: "/min", hour: "/h", day: "/day", week: "/week" };
export const RATE_WORD: Record<RateUnit, string> = { minute: "per minute", hour: "per hour", day: "per day", week: "per week" };
export function rateUnit(r: number | null | undefined, over?: string | null): RateUnit {
  if (over && over in RATE_PER_HOUR) return over as RateUnit;
  if (r == null || !Number.isFinite(r) || r === 0) return "hour";
  return Math.abs(r) > 60 ? "minute" : Math.abs(r) < 1 ? "day" : "hour";
}
export const rateIn = (r: number | null | undefined, unit: RateUnit) => (r == null ? r : r * RATE_PER_HOUR[unit]);
/** "12 alerts/min"; ``over`` is the flow's own rate unit (status.rate_units[flow]). */
export function rateText(r: number | null | undefined, unit = "", over?: string | null): string {
  const u = rateUnit(r, over);
  const tail = (unit || "") + RATE_SUFFIX[u];
  return r == null ? "?" + tail : `${fmt(rateIn(r, u))}${unit ? " " : ""}${tail}`;
}

/** The record, when shorter than the window: how long it is (else null). */
export function recordedShort(st: any): number | null {
  return st?.window && st.first && st.recorded != null && st.recorded < st.window * 0.95 ? st.recorded : null;
}
export const ofRecorded = (x: unknown, st?: any): string => {
  const r = recordedShort(st);
  return r == null ? String(x) : String(x).replaceAll("of the time", `of the ${dur(r)} recorded`);
};
/** A condition or setpoint as printed: <= as ≤, >= as ≥, == as =, != as ≠, a real minus. */
export const op = (x: unknown, st?: any): string =>
  x == null
    ? ""
    : ofRecorded(x, st)
        .replaceAll("<=", "≤").replaceAll(">=", "≥").replaceAll("!=", "≠").replaceAll("==", "=")
        .replace(/(^|[\s(=:])-(?=\.?\d)/g, `$1${MINUS}`);
export const isLimit = (sp: string | null | undefined): boolean => /^\s*[<>]/.test(sp ?? "");
export const holdText = (sp: string, band = "", st?: any): string =>
  `${isLimit(sp) ? "limit" : "setpoint"} ${op(sp, st).replace(/^\s*=\s*/, "")}${(band || "").replace(/^ \((±.*)\)$/, " $1")}`;

/** A goal that went off this many times in the window or more is flapping. */
export const FLAP_AT = 20;
