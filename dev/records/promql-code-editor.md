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

## Where it stopped

Round 2: built, with the definition as the review of round 1 amended it. About 81 net lines outside tests and docs
(budget 600): 110 added, 29 removed.

The amendment (review/promql-code-editor-1): no CodeMirror or any other library, since sessions have no network. Build on
the existing `promql.js` and `sql.js`, which already highlight and complete. Add lists that open at an empty prefix
(after FROM or JOIN the views, a view's columns, PromQL labels inside `{` and after `by(`, label values after `=`) and on
Ctrl+Space, line numbers, bracket matching and the error mark. The text above the first "Where it stopped" is left as it
was; where it says CodeMirror, read the amendment. The `.cm-*` selectors named in round 1's plan do not apply.

What changed:
- `static/codebox.js` (new, shared by both boxes): a gutter of line numbers kept scrolled with the text, and the bracket
  beside the caret drawn with its match (`pq-match`) or as unmatched (`pq-nomatch`). Brackets inside strings and comments
  are not counted. The text is no longer wrapped (`wrap="off"`, `white-space: pre`), so one text line is one gutter line.
- `promql.js`: after `=`, `!=`, `=~` or `!~` in braces, with no quote typed yet, the label's values are listed and the
  pick is put in quotes. Labels after `{`, `,` and `by(`, and values after `="`, already opened at an empty prefix.
  Metrics at an empty prefix open on Ctrl+Space, as before, so a list does not open on every space. The error mark,
  with its UTF-8 column walk, is unchanged.
- `sql.js`: lists open with nothing typed after FROM and JOIN (the views), after `VIEW.` or `ALIAS.` (that view's columns
  only, `ticket t` or `ticket as t`), and where a column comes next (after SELECT, WHERE, BY, ON, AND, OR, HAVING or a
  comma: the named views' columns). SQL's own words are added once a word is begun or on Ctrl+Space.
- The look: the colours are the page's CSS variables, as before, so light and dark follow the theme. No screenshot was
  taken in this session, so that claim rests on the stylesheet and not on a picture.
- SPEC §4e (*The query editor*) and the SQL source's editor paragraph say so.

Acceptance tests (Playwright, each run on its own by test id, all pass):
- done 1: `tests/test_promql_editor.py::test_code_editor_lists_open_before_anything_is_typed_and_the_panel_answers`.
  It picks a metric, a label at an empty prefix after `{`, and a value after a bare `=`. Then the stub source is asked the
  query typed, the preview is drawn with no message, and Ctrl+Space lists the metrics.
- done 2: `tests/test_promql_editor.py::test_code_editor_numbers_lines_matches_brackets_and_marks_the_refusal`. A
  two-line refused query is marked at the `$` (2:3), its lines are numbered 1 and 2, and the bracket at the caret matches
  sum's and then rate's `(`. An unclosed `(` is drawn unmatched.
- done 3: `tests/test_promql_editor.py::test_code_editor_page_loads_with_nothing_asked_beyond_ergostat`. Every request
  not to the test server is aborted and recorded. The page loads, the box mounts, highlights and completes, and nothing
  outside was asked.
- SQL: `tests/test_sql_editor.py::test_code_editor_sql_lists_open_before_anything_is_typed`.
- Seen to fail: with the bare-matcher branch removed (done 1 fails at the values list), with bracketClass returning
  nothing (done 2 fails at the match), with an outside fetch added to codebox.js (done 3 fails on the recorded URL), with
  SQL's views list not opening after FROM (the SQL test fails), and with the gutter not drawn (done 2 fails at the lines).
- The existing tests of both files, run by id after the change, still pass: the 6 in `test_promql_editor.py`, which
  are 7 test ids with the parametrized one, and the 2 in `test_sql_editor.py`.

Left, and why:
- The SQL source gives no place for its errors (`SourceError.at` is never set in `datasources/sql.py`, and SQLite's
  message names a token, not an offset). So the SQL box marks no error. Deriving a place would be a server change outside
  this gap.
- Each box draws its own error mark, gutter and brackets over a textarea. It is not CodeMirror, which the amendment says
  not to use.
- No `## Entry` was written. This record had none, and its definition says it changes only by "Where it stopped".

Done item 4 is kept: the live instance was not touched.
