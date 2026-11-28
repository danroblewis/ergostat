import { useEffect, useRef } from "react";
import { EditorState, Compartment, type Extension } from "@codemirror/state";
import { EditorView, keymap, drawSelection, placeholder as placeholderText } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap, acceptCompletion } from "@codemirror/autocomplete";
import { bracketMatching, syntaxHighlighting } from "@codemirror/language";
import { classHighlighter, tagHighlighter, tags } from "@lezer/highlight";
import { sql, SQLite } from "@codemirror/lang-sql";
import { yaml } from "@codemirror/lang-yaml";
import { lintGutter, setDiagnostics } from "@codemirror/lint";
import { PromQLExtension } from "@prometheus-io/codemirror-promql";
import { suggestClient } from "./promqlClient";
import { addEvents, addShape, emptyShape, expressionCompletion, expressionLanguage, type Shape } from "./expression";
import type { CodeEditorProps } from "./types";

/* A query's text in CodeMirror 6: highlighted (lezer's tokens, drawn as tok-* classes by query-editor.css from the
   page's tokens) and completed at the cursor, a popup the keyboard moves through (arrows, Enter or Tab to take one,
   Escape to close it). SQL completes the views the SQL source reads and their columns (/api/query/fields lists them)
   and SQL's keywords; PromQL is the Prometheus project's own language package, its metric names, label names and
   label values asked of the source (/api/query/suggest), its functions and keywords its own. An expression of the
   event (expression.ts) completes the paths and values of the events it is given and the record's shape. Loaded lazily
   (index.tsx), so the rest of the page does not carry it. */

function language(source: CodeEditorProps["source"], views: Record<string, string[]> | undefined, shape?: () => Shape): Extension {
  if (source === "sql") return sql({ dialect: SQLite, schema: views || {}, upperCaseKeywords: false });
  if (source === "yaml") return [yaml(), lintGutter()];       // a projection's definition (its check errors on their lines)
  if (source === "expression") {                              // an expression of the event (a projection's query)
    return [expressionLanguage, expressionLanguage.data.of({ autocomplete: expressionCompletion(shape || emptyShape) })];
  }
  return new PromQLExtension().setComplete({ remote: suggestClient(source) }).asExtension();
}

// a function's name (PromQL's rate, sum...) a class of its own: classHighlighter calls it a variable
const functions = tagHighlighter([{ tag: tags.function(tags.variableName), class: "tok-function" }]);

export default function CodeEditor({ source, value, onChange, views, label, placeholder, problems, events, shape, onSubmit }: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const lang = useRef(new Compartment());
  const changed = useRef(onChange);
  changed.current = onChange;
  const submitted = useRef(onSubmit);
  submitted.current = onSubmit;
  // a text set from outside is not said back: said back, it would undo an edit made from outside in the same moment
  const outside = useRef(false);
  const known = useRef<Shape>(emptyShape());          // what an expression completes, as it is now
  useEffect(() => {
    const sh = emptyShape();
    if (events) addEvents(sh, events);
    if (shape) addShape(sh, shape);
    known.current = sh;
  }, [events, shape]);

  useEffect(() => {
    const v = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: value,
        extensions: [
          history(), drawSelection(), bracketMatching(), closeBrackets(),
          autocompletion({ activateOnTyping: true, icons: false }),
          keymap.of([{ key: "Tab", run: acceptCompletion }, ...closeBracketsKeymap, ...completionKeymap,
            // a one-line box: Enter (a completion's popup closed: completionKeymap takes it first) says it is done
            { key: "Enter", run: (v) => { const s = submitted.current; if (!s) return false; s(v.state.doc.toString()); return true; } },
            ...historyKeymap, ...defaultKeymap]),
          syntaxHighlighting(functions), syntaxHighlighting(classHighlighter),
          lang.current.of(language(source, views, () => known.current)),
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({ "aria-label": label || `${source} query`, spellcheck: "false" }),
          placeholder ? placeholderText(placeholder) : [],
          EditorView.updateListener.of((u) => { if (u.docChanged && !outside.current) changed.current(u.state.doc.toString()); }),
        ],
      }),
    });
    view.current = v;
    return () => { v.destroy(); view.current = null; };
    // the editor is made once a source (index.tsx keys it by source); its text and views follow below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {                                   // the views arrive after the editor is made
    if (source === "sql") view.current?.dispatch({ effects: lang.current.reconfigure(language(source, views)) });
  }, [source, views]);

  useEffect(() => {                                   // a text set from outside (a shortcut chosen, a source changed)
    const v = view.current;
    if (v && v.state.doc.toString() !== value) {
      outside.current = true;
      try { v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } }); } finally { outside.current = false; }
    }
  }, [value]);

  useEffect(() => {                                   // what check says of the text, on its lines
    const v = view.current;
    if (!v || !problems) return;
    const doc = v.state.doc;
    v.dispatch(setDiagnostics(v.state, problems.map((p) => {
      const line = doc.line(Math.min(Math.max(1, p.line || 1), doc.lines));
      return { from: line.from, to: line.to, severity: "error" as const, message: p.message };
    })));
  }, [problems]);

  return (
    <div className="qe-box" ref={host} data-language={source}
      onKeyDown={(e) => { if (e.key === "Escape" && e.defaultPrevented) e.stopPropagation(); }} />  // Escape closed the popup, not the dialog
  );
}
