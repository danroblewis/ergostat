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

## Where it stopped

Built, round 1: all five points. The code is 51 net lines (trust.py +71/-24, uses.py +15/-11), within budget. The calls below were made alone (headless), each taking the more reversible, fail-closed option:

- **`sources` cannot be written by a template today.** `templates.BODY` has no `sources`, so a template holding `sources:` does not load. `templates.py` is not in this gap's files, so it is unchanged. The gate still lists `sources` in `ALLOWED`, with every key (`type`, `url`, `token-file`, `tls`) under the R3 text rule `T`. `test_sources_entry_gated` tests that rule at the `trust.refused` level, not end to end. Opening `sources:` to templates is its own change.
- **Keys count as pieces.** In a `query` map, each field's value can be the owner's, but if the map's keys (`source:`, `promql:`) are the library template's own words, the whole value is refused. Owner text passes when it is given whole (`query: '${q}'`), or when every key and value is the owner's or a trusted template's. This is stricter than strictly needed and is easy to loosen later.
- **A template's own text whose writer can't be told** (lesson-3). expand.py leaves a field (`${m.q}`, `${it.x}`), an `each:` element and a key made from a value unmarked, outside `run:`. That makes them look like the template's own words. This branch does not touch expand.py, so `trust.blind(t)` reads all of such a template's own text in these four keys as the library's. A trusted template that uses fields anywhere therefore cannot place `ask`/`prompt`/`query` text in a held chain. A whole value given (`Given`) carries its writer down into its leaves, so an owner folder's `sensor: '${how}'` holding a library map is refused. The same unmarked-field path still reaches the `W` keys (`every`/`cron`/`timeout`/`averages`) of a trusted template. That is outside this gap; it is noted here, not fixed.
- **`ai`/`person` tables.** `MACHINE_TYPES` (program, ai, person) replaces `PROGRAM` and the three types' `REFUSED_TYPES` entries. All three share one `MACHINE_NO` listing every machine key by name. `program`'s allowed keys are unchanged (goal, run, every, cron, timeout). `ai` and `person` allow only their text, goal, until, every and cron. `timeout` stays refused for them, since the definition names only goal/until and every/cron. `test_every_compile_key_classified` now checks each machine type's table against compile's `TYPE_KEYS` and its `sources` keys against `SOURCE_TYPES`.
- **Refusal order.** The first refused path decides the code. A part with both a library `prompt` and a `model` reports whichever key comes first.
- **Point 4's "same template compiles":** an owner-folder run can take only an owner command passed whole (R1). So the case that compiles is that template with `run: '${x}'` and `x: {type: command}`, given the owner's `${cmd}` wholly. `sh -c ${x:quote}` is refused for a library literal, and an owner value would not compile there either.
- **Not in this gap:** `bounds.STARTED` is program, ai and judge, so a held chain's `person` block gets no compile-time `untrusted-limit` floor. Its `every`/`cron` must still be the owner's or a trusted template's (`W`), and `pace()` floors its clock at run time.
- **Merge:** this clone has only `main` and this branch (no remote-tracking refs). `main` is an ancestor of HEAD, so there was nothing to merge.
- **Lesson-9 breaks, each seen to fail:**
  - key back to `NO` (`query`/`prompt`/`ask`): 8 failures (gated ×3, mixed, other-keys ×3, try_use[ask]).
  - any owner mark enough: `test_untrusted_text_mixed_value_refused` and `test_sources_entry_gated`.
  - code left `library-untrusted`: gated ×3, mixed, try_use[ask].
  - `blind()` returning False: the mixed test's `${m.q}` case.
  - a `Given`'s writer not carried down: the mixed test's `${how}` case.
  - `test_try_use_runs_nothing_when_refused` guards code main already had (author.trial returns before starting a process when check has errors). No break of that code was tried.
