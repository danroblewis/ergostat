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
