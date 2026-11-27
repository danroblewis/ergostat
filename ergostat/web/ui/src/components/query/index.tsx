import { lazy, Suspense } from "react";
import { useApi } from "../../hooks/useApi";
import type { QueryEditorProps } from "./types";
import "../../styles/query-editor.css";

export { LivePreview } from "./LivePreview";
export type { QueryEditorProps } from "./types";

/* A query in its source's own language: <QueryEditor source="sql" | "promql" value onChange />. The editor
   (CodeEditor.tsx, CodeMirror) is its own chunk, loaded the first time one is drawn; until then a plain text box
   holds the text. For SQL it completes the views /api/query/fields lists under the sql source, with their columns. */
const CodeEditor = lazy(() => import("./CodeEditor"));

interface Listed { datasources?: { name: string; views?: Record<string, string[]> }[] }

export function QueryEditor(props: QueryEditorProps) {
  const fields = useApi<Listed>(props.source === "sql" ? "query/fields" : null, {}, { window: false });
  const views = fields.data?.datasources?.find((d) => d.name === "sql")?.views;
  return (
    <div className="qe">
      <Suspense fallback={
        <textarea className="qe-fallback" value={props.value} spellCheck={false} rows={4} aria-label={props.label || `${props.source} query`}
          placeholder={props.placeholder} onChange={(e) => props.onChange(e.target.value)} />
      }>
        <CodeEditor key={props.source} {...props} views={views} />
      </Suspense>
    </div>
  );
}
