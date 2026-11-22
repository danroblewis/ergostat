# library-provenance-join-1: in a held chain, `ask`, `prompt`, `query` and `source` pass when no piece of them is library-written and are refused as `untrusted-text` otherwise; `try_use` on a refused use runs nothing; and the stricter owner-folder rule is recorded with its test
depends-on: [library-provenance-marks]

## Definition of done

Built on library-provenance-marks: writer marks, `run_ok` and `writer_ok` in `ergostat/library/trust.py`, and the chain check in `ergostat/library/uses.py`.

1. **R3, writer-based text.** These values may now appear in a chain that holds an untrusted template, with no library-written piece in them: a person block's `ask`, an ai block's `prompt`, a sensor's `query` (its `source:` and every field) and a `sources` entry (every value in it). Pieces written by the owner or by a trusted template are fine. The `ai` and `person` block types stop being refused by type. Their other keys stay refused by name (`model`, `run`, `parse`, `context`, `review`, `agent`, `workspace` and the rest). Only `goal`/`until` are allowed, and `every`/`cron` keep the writer rule `W`. A value whose writer can't be told counts as library-written: a missing mark, a `Given` with no meta, the field marker `F` or a mark character outside a mark.
2. **Its own refusal.** When one of these four keys holds a library-written piece, the whole use is refused as before, with nothing of it put in the model. The problem's code is `untrusted-text` instead of `library-untrusted`, and the refusal suggests no copy into `with:` and does not quote the value. Every other refusal keeps `library-untrusted`.
3. **try_use.** On an instance the gate refuses, the MCP `try_use` reports `ran: false` and starts no process. Main already does this; this branch adds the test.
4. **R2's safe forms: the stricter rule stands.** An owner-folder template's run takes no library value, `${x:quote}` included, because `sh -c ${x:quote}` runs whatever lands in it. An unquoted `${x}` of a `string` is refused too. SPEC §2a and GAPS say plainly that this rule replaces the parent's "quoted library literal accepted in trusted text" and why. The same template given the owner's own value still compiles.
5. SPEC §2a, SECURITY *Libraries you did not write*, the AGENT-GUIDE and the GAPS Shared-libraries entry describe R3 and `untrusted-text`. The "`ask:` and `query`/`source` gated past the allowlist" item leaves *Still needed*. `test_every_compile_key_classified` still passes, so every newly reachable ai/person key is classified.

## Relation to other work
- library-provenance-marks (merged): builds on its marks, `writer_ok` and owner-folder rule; changes no expansion.
- library-sandbox-blocks (ready): it touches `expand.py`; this branch avoids that file and changes only the gate tables and the refusal code.
- library-sandbox-sensors (ready): it touches `spec/compile.py`, `spec/ir.py` and `sensing.py`; this branch leaves them alone.
- library-fetch (ready): it touches other `ergostat/library/` modules, not `trust.py` or `uses.py`.

## Files to touch
- `ergostat/library/trust.py`
- `ergostat/library/uses.py`
- `tests/test_library_provenance.py`
- `tests/test_library_trust.py`
- `docs/SPEC.md`
- `docs/SECURITY.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`

## Risks
- lesson-3: a value whose writer can't be told (unmarked, a `Given` without meta, a nested map's leaf) is read as the owner's, so library text passes. Every unknown writer must count as library.
- lesson-8: the gate is called a guard, so it must stay an allowlist. Opening the `ai`/`person` types must not let their other keys through, and the docs must not claim more than "no library-written piece".
- lesson-9: a test that only shows refusal can't tell R3 from main's blanket refusal. Each test pairs a refused case with an owner case that compiles, and the report says which break (key back to `NO`, any owner mark accepted, or code left as `library-untrusted`) made each test fail.

## Acceptance tests
- `tests/test_library_provenance.py::test_ask_prompt_query_gated`: for each of `ask`, `prompt`, sensor `query` and a `sources` entry, a library literal or default is refused with code `untrusted-text` and nothing of the use is in the model. The owner's whole `with:` value in the same slot compiles. Fails on main, and again if the owner value is refused.
- `tests/test_library_provenance.py::test_untrusted_text_mixed_value_refused`: the owner's value with library words around it (`"${q} and more"`), and a `query` map with one library field, are both refused with `untrusted-text`. Fails if any owner mark is enough to pass.
- `tests/test_library_provenance.py::test_ai_person_other_keys_still_refused`: a held ai block with an owner-whole `prompt` plus a `model`, `run` or `context` is refused as `library-untrusted` at that key.
- `tests/test_library_provenance.py::test_try_use_runs_nothing_when_refused`: a refused instance whose sensor or block command would touch a marker file goes through `try_use`. Afterwards the marker is absent and the result has `ran: false`, with the refusal among its check errors.
- `tests/test_library_provenance.py::test_safe_forms_in_trusted_text`: an owner-folder template running `sh -c ${x:quote}`, given an untrusted template's literal, is refused. A `string` placed as `${x}` is refused. The owner's whole value in the same template compiles.
- `tests/test_library_trust.py::test_every_compile_key_classified`: still passes with the `ai`/`person` keys now reachable.

## Size budget
90 net lines
size: M (confidence: medium)
