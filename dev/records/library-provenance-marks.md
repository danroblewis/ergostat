# library-provenance-marks: values carry who wrote them through expansion and nested uses, so a held chain may run the owner's own `type: command` values, and pass only short, checked library values as arguments to ergostat's own programs
depends-on: [library-trust-folders]

## Definition of done

This builds on library-trust-folders: held chains, trust.py and `library-untrusted`. It loosens the gate in exactly two places and nowhere else.

1. **Writers.** Every parameter value has a writer:
   - **owner**: written in the owner's model files, in a depth-0 `with:`;
   - **trusted**: a built-in or owner-folder template's literal, default or `|default`;
   - **library**: written by an untrusted template (literal, default, `|default` or interpolated text).

   A nested `with:` value that is wholly one `${p}` (no `:how`, no `|default`, no `.field`) keeps p's writer. Anything else is library-written if any part of it is library-written; otherwise it belongs to the template writing it. A value is an **owner command** only if the owner wrote it into a `type: command` parameter and it reached every later hop wholly, again as a `type: command` parameter. A hop through any other type drops the command status. Equality to text the owner wrote elsewhere never counts.
2. **Marks.** `expand.py`'s marks around substituted text (`A`/`B`) also carry the writer, and the type for library values. They are kept until the gate has judged the instance's sections, then stripped as now. `rename()` and `remote/compose.py` behave as before; this is covered by the existing tests.
3. **R1, the owner's commands.** In a held chain, a program block's `run` and a sensor's `run` are allowed when every character of them is one of:
   - (a) text marked owner command, when it is the whole value;
   - (b) inside a built-in template's run slot, a built-in literal, a built-in name (`${lib}`, `${python}`, `${name}` of the instance) or an owner command substituted through `:quote`/`:arg`;
   - (c) a library value allowed by point 4.

   Any library literal text (an untrusted template's own words around `${cmd}`, its `${here}`, a library default for a command parameter) refuses the chain. So does an owner value of any other type, such as a `string` parameter. Every other key that library-trust-folders refuses stays refused. That includes `every`, `cron` and `timeout`, which are allowed only when their writer is the owner or trusted (the minimum `every` for library values is library-untrusted-text's), and also `parse`, `max`, `pool`, `lease`, `agent`, `workspace`, `actions`, `network`, `prompt` and `ask`.
4. **R2, library values as arguments to ergostat's programs only.** A library-written value may appear in a run slot only when all of these hold:
   - the slot is in a **built-in** template and starts with `${lib} `;
   - the value directly follows a flag in trust.py's allowlist `LIB_DATA_FLAGS` (flags of `ergostat.library.run` whose value is data, never run: e.g. `--kind`, `--name`, `--limit`, `--every`). Never after `--run`, `--render`, `--command` or anything else;
   - its parameter type is one of name, duration, number, integer or bool;
   - the text that lands in the slot (after `:seconds`/`:hours`) fully matches its type's pattern. These are stated in SPEC and SECURITY and tested:
     - name `[a-z][a-z0-9-]{0,63}`;
     - duration `[0-9]{1,9}(\.[0-9]{1,6})?(ms|s|m|h|d|w)?`;
     - number or integer `-?[0-9]{1,15}(\.[0-9]{1,9})?`;
     - bool: the bare flag, or `true`/`false`.

   Python's `NAME.match` and the duration regex accept a trailing newline and spaces; these checks use `fullmatch` with no whitespace. A library value of any other type (string, strings, url, path, map, list, glob, cron, setpoint, any) never reaches a run slot. A library value never reaches the run slot of an **owner-folder** template (such as `sh -c ${x:quote}`), because no test can vouch for one. Such a chain is refused even though the template itself is trusted.
5. **Nested refusals.** These follow library-trust-folders' rule: the whole chain from the owner's `use:` is refused, with the error at that line and no part of any template in it in the spec. The message never quotes the value and never suggests `with:` or copying a command.
6. **Docs:**
   - SPEC §2a covers writers, owner commands, R1, R2 with the patterns, and the owner-folder rule.
   - SECURITY *Libraries you did not write* says what runs: the owner's own commands, and ergostat's programs with checked arguments. It also says what it does not stop: a library can choose the kinds and states the owner's command runs on, and an agent that writes the owner's `with:` makes a value the owner's.
   - AGENT-GUIDE: never copy a command from a library into `with:`; ask the owner.
   - GAPS is updated.
7. **House rules,** as library-trust-folders.

## Files to touch
- `ergostat/library/expand.py`
- `ergostat/library/trust.py`
- `ergostat/library/uses.py`
- `docs/SPEC.md`
- `docs/SECURITY.md`
- `docs/AGENT-GUIDE.md`
- `docs/GAPS.md`
- `tests/test_library_trust.py`
- `tests/test_library_provenance.py` (new)

## Risks
- **lesson-8:** "a library's text never runs" is false if a trusted template places a library string where it runs (`sh -c ${x:quote}`), if a name like `rm` lands at a command's head, or if a value carries a newline. Four things guard against it:
  - narrow types only, checked by fullmatch on the rendered text;
  - only built-in `${lib}` slots, and only after allowlisted data flags;
  - `test_builtin_run_slots_take_narrow_values_only_as_arguments`, which runs over every built-in template;
  - `test_every_lib_flag_classified`.

  Owner-folder templates get no library values in run slots at all. The docs say exactly this and no more.
- **lesson-3:** each of these must count as library-written, never as owner or trusted:
  - a value whose writer can't be told (e.g. marks lost through `strip` in a nested `with:`);
  - an element field `${it.x}`;
  - a `|default`;
  - a `.first`/`.count` field.

  Covered by `test_command_mark_lost_through_non_command_param` and `test_library_default_for_command_param_refused`.
- **lesson-9:** each test is broken once and seen to fail, and the report says so: writer forced to owner, the fullmatch turned back into `match`, an owner-folder template allowed, `--run` added to `LIB_DATA_FLAGS`. The built-in scan is also fed a fixture template it must flag.
- **lesson-7:** merge origin/main. library-untrusted-text may have changed how `every` is treated in untrusted output; keep exactly one rule and run both suites again.
- **Not applicable here:** lessons 1, 2, 4, 6 and 11 (no concurrency, timing, counts or destructive paths).

## Acceptance tests
Unless marked otherwise, all of these are in `tests/test_library_provenance.py`.
- `test_owner_command_whole_slot_allowed`: an untrusted template's program block with `run: ${cmd}`, where the owner gives `cmd` (type command), compiles. Its `run` equals the owner's text.
- `test_owner_command_through_builtin_allowed`: untrusted L uses built-in `collect`, with `command: ${cmd}` from the owner and a library-written `kind: tickets`, and leaves `poll` at collect's default. It compiles, and the run holds the quoted command and `--kind tickets`.
- `test_library_every_refused`: the same, with L writing `poll: 1m`. Refused.
- `test_library_literal_equal_to_owner_command_refused`: L writes, as a literal, the same text the owner wrote elsewhere. Refused.
- `test_library_default_for_command_param_refused`: an untrusted template's command parameter with a `default:` that is left unset. Refused.
- `test_library_text_around_owner_command_refused`: `run: "${cmd} | sh"` in L, and a nested `command: "${cmd}; x"`. Both refused.
- `test_owner_string_param_in_run_refused`: an owner value given to a `type: string` parameter reaches `run`. Refused.
- `test_command_mark_lost_through_non_command_param`: the owner's command goes into L's string parameter, and L passes that to collect's `command`. Refused.
- `test_nested_library_literal_refused`: the owner uses L, L uses untrusted L2, and L2 passes a literal command to `collect`. There is one error at the owner's line. No system, item, stock, flow, block or `doc.uses` entry of L, L2 or collect is in the spec.
- `test_library_value_into_owner_folder_template_run_refused`: L passes a valid name to an owner-folder template whose run is `sh -c ${x:quote}`, and also to one whose run is `${lib} each --kind ${kind}`. Both are refused.
- `test_narrow_value_patterns[...]`: library-written values given to collect or re-ping. These are refused: `"rm\n"`, a 65-character name, `Tickets`, `"5m\n"`, `" 5m"`, `1e3s`, `1e9`, `nan`. `tickets`, `5m`, `1.5h` and `3` are allowed.
- `test_builtin_run_slots_take_narrow_values_only_as_arguments`: scans every built-in template, including the `*/template.yaml` ones, and every run slot. Each `${p}` in a slot must be one of:
  - a built-in name;
  - a command parameter, whole or through `:quote`/`:arg`;
  - a narrow-typed parameter directly after a flag in `LIB_DATA_FLAGS`, in a slot starting `${lib} `.

  Any other parameter type must be one trust.py refuses from a library. A fixture template containing `sh -c ${kind}`, `--run ${kind}` and `${title:quote}` (string) must be flagged by the same checker.
- `test_every_lib_flag_classified`: every option of every `ergostat.library.run` subcommand's argparse parser is in `LIB_DATA_FLAGS` or `LIB_EXEC_FLAGS`, and the two are disjoint. A parser with an extra option added is reported.
- `test_refusal_never_suggests_with`: no refusal message contains `with:`, `trust: owner` or the refused value.
- `tests/test_library_trust.py`: all of its tests still pass. The existing tests in `tests/test_templates.py` (renaming, `if`/`each`) and the remote compose tests pass unchanged.

## Size budget
320 net lines outside tests and docs: expand.py about 110 (writer marks, writers of nested values), trust.py about 140 (slot judging, patterns, flag lists), uses.py about 40 (writers passed to nested uses, marks kept until the gate).

## Notes from the plan review (answer each; not blocking)

- Marks now carry the writer, but nothing stops library text or values from containing the A/B mark characters and forging an owner-command mark. Add a rule that only expand.py makes marks and that any template text or value containing a mark character is refused, plus a test that forges an owner mark and is refused (broken once and seen to fail). Name it under lesson-8 and lesson-3.
- R2 allows library values after rate and count flags (--every and --limit in LIB_DATA_FLAGS) with no bounds: the duration pattern accepts 0/0ms and integers go up to 15 digits. That bypasses R1's minimum every for library values and contradicts test_library_every_refused (collect's poll can land as --every in the run slot). Lesson-4 is wrongly called not applicable. Either drop rate and count flags from LIB_DATA_FLAGS or give each one a bound in trust.py, with tests that a library '--every 0ms' and an oversized '--limit' are refused.
