# promql-code-editor: the query box is a real code editor

The owner, 2026-11-23: "I also wanted the promql text editor to be a code editor with syntax highlighting and autocomplete based on metric names and label names and label values." Today `ergostat/web/static/promql.js` is a textarea with an overlay. It completes metric names, but it does not look or behave like a code editor.

Change. Use a proper editor component (CodeMirror 6, vendored into the static files, no CDN and no build step at runtime) for every data-source query box (PromQL first, then SQL):
- syntax highlighting for PromQL (metrics, labels, strings, functions, durations, operators) and SQL;
- autocomplete for metric names, label names inside `{}` and `by()`, label values after `=`, `!=`, `=~`, and PromQL functions, from `/api/query/suggest`;
- line numbers, bracket matching, multi-line editing, Ctrl/Cmd+Enter to run, and the source's error marked at its place;
- the same look in light and dark themes.

Definition of done.
1. A browser test types a query and picks a metric, a label name and a label value from the completions, and the panel answers.
2. A browser test shows a refused query marked at the right place.
3. The page loads with no network access beyond ergostat's own server.
4. Do not measure or change the live instance in the session.

## Where it stopped

Round 1: not built. Nothing outside this record changed. The gap waits for CodeMirror 6 to be put into the tree.

Why: this definition's core is "CodeMirror 6, vendored into the static files". This session has no network, and no
copy of CodeMirror 6 (or any `@codemirror/*` / `@lezer/*` package) is anywhere in the repository (a search for
`codemirror` finds only this record and `promql-editor.md`). Session tools cannot read anything outside `/work`. The
earlier gap `promql-editor` hit the same wall and built ergostat's own textarea-plus-overlay editor instead
(`promql.js`, `sql.js`). This gap was opened because the owner does not want that kind of editor any more. A second
home-made editor would go against the definition, and CodeMirror written from memory would not be the real,
pinned library. So the most reversible choice is to change nothing and say what is needed.

What is needed first (a session with network, or the owner):
- One pre-built ES-module or IIFE bundle of CodeMirror 6 at a pinned version, put under
  `ergostat/web/static/codemirror/` with its LICENSE (MIT) and a README naming the version and the packages, the way
  `uplot/` and `libavoid/` are vendored. Packages: `@codemirror/state`, `view`, `language`, `autocomplete`,
  `commands`, `lint`, `lang-sql`, and optionally `@prometheus-io/codemirror-promql` or a small PromQL
  `StreamLanguage` in ergostat's own code.

What is left once the bundle is in the tree (all in this gap, within the 600-line budget):
- Replace the bodies of `promql.js` and `sql.js` behind the same `window.queryEditors[language](...)` contract
  (`{el, area, set, mark}`) that `panel-editor.js` already uses, so the panel editor does not change.
- PromQL highlighting via a StreamLanguage tokenizer (metrics, labels, strings, functions, durations, operators); SQL
  via `lang-sql`.
- A completion source that calls the existing `/api/query/suggest` (metrics, labels in `{}` and `by()`, values after
  `=`, `!=`, `=~`, plus functions). The server side is already built and bounded (`promql-editor`).
- `lineNumbers`, `bracketMatching`, a Mod-Enter keymap calling `onRun`, and a lint diagnostic at `error_at`. The
  UTF-8-byte column walk in `promql.js`'s `offsetOf` must be kept.
- A theme that reads the page's existing CSS variables, so light and dark look the same.
- Acceptance tests: carry `tests/test_promql_editor.py` over to CodeMirror's DOM (`.cm-content`,
  `.cm-tooltip-autocomplete`, `.cm-lintRange-error`) for done 1 and 2. Add a browser test that blocks every request
  not addressed to the test server and checks the page still loads and the editor mounts, for done 3.

Done item 4 is kept: the live instance was not touched.

## Where it stopped

Parked by the factory (review/promql-code-editor-1, 2026-11-23 23:27).

Nothing is built. The branch holds only the definition of done and a 'Where it stopped' section. All the editor work (CodeMirror-based promql.js and sql.js behind the existing window.queryEditors contract, PromQL highlighting, completion from /api/query/suggest, line numbers, bracket matching, Mod-Enter to run, a lint mark at error_at, a theme that reads the page's CSS variables) and the browser tests for done 1-3 are left. It stops because the definition requires a vendored CodeMirror 6, which is not in the tree and could not be fetched in a session without network. The server side (/api/query/suggest) is already built.
