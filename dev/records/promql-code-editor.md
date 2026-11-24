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
