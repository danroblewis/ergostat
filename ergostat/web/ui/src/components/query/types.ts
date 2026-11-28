/** What the query editor is given: the source the text is asked of (ergostat has two, promql and sql), the text, and
    what it says when the text changes. */
export interface QueryEditorProps {
  source: "sql" | "promql" | "yaml" | "expression";
  value: string;
  onChange: (text: string) => void;
  label?: string;
  placeholder?: string;
  /** what check says of the text, each on its line (1-based; none: the first), drawn in the editor (a YAML body's) */
  problems?: { line?: number | null; message: string }[];
  /** an expression's: events the record holds (the query's sample), whose paths and values it completes */
  events?: { type?: unknown; item?: unknown; source?: unknown; data?: unknown }[];
}

/** The editor itself (CodeEditor.tsx, loaded lazily): also the SQL source's views and their columns, to complete. */
export interface CodeEditorProps extends QueryEditorProps {
  views?: Record<string, string[]>;
  /** an expression's: GET /api/events/shape's paths, completed as well as the events' */
  shape?: { path: string; examples?: unknown[] }[];
}
