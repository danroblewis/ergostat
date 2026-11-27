import type { PrometheusClient } from "@prometheus-io/codemirror-promql";
import { apiGet } from "../../lib/api";

/* The PromQL language package asks a Prometheus for names; here it asks ergostat (GET /api/query/suggest), which asks
   the source's VictoriaMetrics, bounded, for this project's names only. A name the source cannot give is no
   suggestion, never an error in the editor. */
type What = "metrics" | "labels" | "values";

export function suggestClient(source: string): PrometheusClient {
  const ask = (what: What, prefix = "", metric = "", label = ""): Promise<string[]> =>
    apiGet<{ suggestions?: unknown[] }>("query/suggest", { source, what, prefix, metric, label })
      .then((got) => (got.suggestions || []).map((s: any) => (typeof s === "string" ? s : s?.name)).filter((s): s is string => !!s))
      .catch(() => []);
  return {
    metricNames: (prefix?: string) => ask("metrics", prefix || ""),
    labelNames: (metric?: string) => ask("labels", "", metric || "").then((names) => names.filter((n) => n !== "__name__")),
    labelValues: (label: string, metric?: string) => ask("values", "", metric || "", label),
    metricMetadata: async () => ({}),
    series: async () => [],
    flags: async () => ({}),
  };
}
