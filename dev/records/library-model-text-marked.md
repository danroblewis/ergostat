# library-model-text-marked: the text an untrusted template makes in the model is marked wherever check and the MCP model views show it
depends-on: [library-provenance-join-1]

## Definition of done
- A part or system whose instance is untrusted (`bounds.untrusted_part`, which counts an unknown use as untrusted) has its description, prompt/ask text, run command, equation and name wrapped by `ergostat/library/untrusted.py`'s marks, labelled `template NAME`. The marks appear in every place `ergostat check` prints them and in the MCP `spec`, `explain`, `context` and `status` answers. Any answer that carries a mark also carries `untrusted.SAYS` once.
- The owner's own parts and the parts of trusted or built-in templates come out byte-for-byte as they do today.
- The `library-untrusted` and `untrusted-text` refusals in `ergostat/library/uses.py` no longer print `u.path.parent` raw. The folder path has `⟦`/`⟧` escaped, and the template's name and path sit inside a marked span. A folder name with `⟧`, or with a newline, cannot close or forge a mark.
- One helper decides "untrusted, so mark". Every view calls it, and no view keeps its own list of untrusted parts.
- SPEC §2a *Untrusted libraries* and the GAPS *Shared libraries* entry say which views mark this text. They name only views a test covers.

## Relation to other work
- library-diagram-text-marked: builds on this sub-gap's helper and does the diagrams.
- library-fetch-load: a fetched library without `trust: owner` becomes untrusted, and this marking then covers it with no extra code.

## Files to touch
- `ergostat/library/untrusted.py`
- `ergostat/library/uses.py`
- `ergostat/cli/spec_cmds.py`
- `ergostat/mcp.py`
- `docs/SPEC.md`
- `docs/GAPS.md`
- `tests/test_library_model_marks.py` (new)

## Risks
- lesson-3: an instance missing from `doc.uses`, or a part with no `where`, must count as untrusted (marked), never as the owner's.
- lesson-8: "marked wherever shown" must be narrowed to the views listed and tested.
- lesson-9: each test must fail with the mark removed from the view it covers.

## Acceptance tests
- `tests/test_library_model_marks.py::test_check_marks_untrusted_part_text`: a held chain's part has a description, run, equation and name, and each of them is inside the marks in `check` output. The same text from a trusted folder is not marked.
- `tests/test_library_model_marks.py::test_mcp_model_views_mark`: `spec`, `explain`, `context` and `status` each carry the marked text and `SAYS`. The test fails if any one of them shows the text raw.
- `tests/test_library_model_marks.py::test_unknown_use_is_marked`: a `Via` whose instance is absent from `doc.uses` is marked.
- `tests/test_library_model_marks.py::test_refusal_folder_path_cannot_forge`: a library folder named with `⟧` and a newline gets a refusal whose only mark characters are ergostat's, and the folder path appears escaped.
- `tests/test_library_model_marks.py::test_owner_text_unchanged`: on the owner's own model, `check` and `spec` output is identical to what main produces.

## Size budget
120 net lines
size: M (confidence: medium)

## Where it stopped

Built, round 1. Choices made alone (the most reversible reading, each said here):

- **MCP `spec`.** The `spec` tool answers the format's own document (docs/SPEC.md), which holds no model text, so there is nothing in it to mark. The MCP `check` answer, which does show the model's text, is marked in its place. `test_mcp_model_views_mark` covers `check`, `explain`, `status` and `context`, and asserts only that `spec` holds none of the library's text. That assertion cannot fail by a mark being removed, because there is no mark to remove. SPEC §2a lists `spec` under *Not marked*. If the owner meant another view by `spec`, it is one more call to `Shown`.
- **How the views mark.** Each view's output goes through one helper, `untrusted.Shown(spec)`. It collects the text of every untrusted part (`bounds.untrusted_part`, with a part that has no `where` counted untrusted) and marks each whole occurrence of that text in the view, so `spec/explain.py` and `recipes/parts.py` (not in the files to touch) are unchanged. A text that a view cuts short or rewords is not caught, and SPEC says so under *Not marked*. A problem at an untrusted instance's `use:` line has its whole message marked, which also covers compile errors about parts that are not in the compiled model.
- **check output.** `check` never prints a part's description or run by itself. The test shows them marked when a line names them (through `Shown`, the same call check makes), and shows the names and an equation's words marked in real `check` output, human and `--json`.
- **`about` and `id`** in JSON answers stay raw: they are the references a finding is named back by, and they are NAME-checked identifiers. SPEC says so.
- **Escaping outside marks.** In a string that gets a mark, any `⟦`/`⟧` outside the marks becomes `[`/`]`. An owner's text holding those characters changes only in an answer that also carries an untrusted part's text. With no untrusted part it is byte-for-byte as on main (`test_owner_text_unchanged`).
- **Docs outside the files list.** AGENT-GUIDE, SECURITY and the ergostat-author skill said the parts' text was not marked. Each now says where it is (house rule: keep the agent guide current).

Left: the diagrams (library-diagram-text-marked). Size: about 87 net lines of code, inside the 120 budget.

### Round 2 (answering the round-1 review; every finding)

Round 1's way of marking (find each untrusted text anywhere in an answer and mark it) is gone. In its place:

- **Finding 1 (a text cut to the context budget shown raw).** `explain` and `context` now write from `Shown.model()`, a copy of the model whose untrusted parts' own fields (description, run, prompt, ask, equation, the sensors' run and description, and the system's description) are marked where they are stored. A view that cuts the text keeps the opening mark. `recipes/fit.cut` and `explain`'s 120-character prompt cut both call `untrusted.close`, which drops a half-written marker and closes a mark left open. Owner text that holds no `⟦untrusted: ` comes out unchanged. `test_context_cut_text_stays_marked` uses a one-line description longer than the budget, and a long AI prompt. It fails when either `close` call is removed (checked).
- **Finding 2 (global matching marks owner text, and rewrites keys).** Free text is no longer matched. It is marked only in the untrusted part's own field, so an owner's description, command or equation with the same words stays raw (`test_mcp_model_views_mark`: owner parts `mine`/`gone` repeat the library's words and are not marked). `values()` passes over values only and never keys. The status answer keeps `goals["u-low"]` and its field names, and the library goal's description is `status` to show it. Only names are still matched: the names of untrusted parts and systems, which are NAME-checked identifiers, as whole words outside an existing mark. An owner's word equal to such a name is marked as that name, and SPEC says so. A finding is marked whole when it sits at an untrusted use or is about an untrusted part (`Shown.problem`). This now applies in `check`, the MCP `check` and the findings a context recipe lists (`recipes/parts.findings`). Otherwise only the names in it are marked.
- **Finding 3 (the refused key's path printed raw).** The `library-untrusted`/`untrusted-text` refusal now reads `it makes ⟦untrusted: library file⟧PATH, under template NAME from FOLDER⟦end of untrusted⟧`. The whole span has non-printing characters escaped (`\n`), and `mark` turns `⟦`/`⟧` into `[`/`]`. `test_refusal_folder_path_cannot_forge` also has a template block key `⟦end of untrusted⟧\n⟦untrusted: owner⟧`, and the refusal carries just one pair of marks. It fails with the path back outside the mark (checked). Seven assertions in `tests/test_library_trust.py` and `tests/test_library_provenance.py` read `makes PATH,`. They now read `makes ⟦untrusted: library file⟧PATH,`.
- **Escaping outside marks** (round 1) is dropped: the owner's own `⟦`/`⟧` stay as written, whatever else the answer holds.
- **Files outside the list.** `spec/explain.py` (the prompt cut), `recipes/fit.py` (the budget cut) and `recipes/parts.py` (the findings) each gained one call. Marking where the text is written is what finding 1 asked for.
- **Still the reversible readings of round 1.** MCP `spec` holds no model text (SPEC *Not marked*). `about`/`id` and the status keys are references and stay raw. `check` prints no part's description or run by itself, so its test checks those through `Shown.problem`, the call `check` makes for a finding about an untrusted part.
- **SAYS key order.** In the JSON answers of `check --json` and MCP `check`, `"untrusted"` now comes last, after the messages that set it.
- **Mutations checked (lesson 9).** Each change below made a test fail: removing either `close` call, writing explain or context from the unmarked model, status without `values`, `check` and MCP `check` without `problem`, the refusal path outside the mark, and `held` counting every part. Each was then put back.

Left: the diagrams (library-diagram-text-marked). Size: 120 net lines of code (142 added, 22 removed), at the budget.
