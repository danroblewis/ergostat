/** What the query editor is given: the source the text is asked of (ergostat has two, promql and sql), the text, and
    what it says when the text changes. */
export interface QueryEditorProps {
  source: "sql" | "promql";
  value: string;
  onChange: (text: string) => void;
  label?: string;
  placeholder?: string;
}

/** The editor itself (CodeEditor.tsx, loaded lazily): also the SQL source's views and their columns, to complete. */
export interface CodeEditorProps extends QueryEditorProps {
  views?: Record<string, string[]>;
}
