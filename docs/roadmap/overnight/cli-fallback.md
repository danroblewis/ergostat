# cli-fallback: the command line on the last good model while the YAML is broken

Branch `cli-fallback`, from origin/main at dd91518. Resumes item 1 of `resilience` (parked after two failed gates;
`git show resilience:docs/roadmap/overnight/resilience.md`, "Where it stopped"), built again from main, not carried
over.

## The gap

`docs/GAPS.md`: **the CLI refuses to run while the YAML is broken**, so `ergostat status`, `item`, `event` and the
model's numbers (`fit`, `residual`, the parts) fail while an agent edits, and so does every sensor and block that
reads the record through `$ERGOSTAT_CMD`. The parked fallback failed three ways: it never kept AI models with prompt
files; it ran commands in its copy of the files; and it mixed the kept YAML with include files read live from disk,
loading a model that never existed.

## Definition of done

Every file the model's loading reads (the main file, its includes and what their globs matched, prompt files, the
library's templates, remotes' cached models; and every file it looked for and did not find) is read through one
place, `ergostat/spec/files.py`, which notes what it read. When the engine takes a model (at start, and at each change
it takes) it keeps that model whole as one snapshot: each file's bytes stored once by their SHA-256 in
`<state>/good/objects/`, and one manifest (`good/manifest.json`, replaced atomically) naming every path read with its
hash, every path found missing, and every glob with what it matched. A snapshot is kept only when it reads back
clean. The fallback loads **only** from that snapshot: every read, glob and existence check is answered from the
manifest, a path the snapshot does not hold fails the fallback (it is never read from disk), and while it loads
nothing may be opened or listed in the model's folders, and no process or connection started (a Python audit hook
refuses them). The model it gives has its real paths, so the project is the repository's, never a copy. Only
commands that read fall back: `status`, `item`, `event`, `lease`, `loop`, `system`, `explain`, `findings`, `residual`,
`fit`, `claims`, `messages`, `agent`, `block`, `inbox` and the parts, with none of their acting flags (`event --add`,
`block --now`, `lease --nack`, `inbox --approve`, ...), with one warning line on stderr naming the YAML's error and
when the model was taken. Every other command, and these with an acting flag, refuses with the YAML's errors and one
line saying it acts, so it never runs on the last good model. `check` reports the edited model's errors as now.
SPEC §9.1 and AGENT-GUIDE say so.

## Acceptance tests (`tests/test_cli_fallback.py`)

- `test_status_item_and_event_read_the_record_with_the_last_good_model_while_the_yaml_is_broken`
- `test_acting_commands_refuse_naming_the_yaml_error`
- `test_check_still_reports_the_edited_models_errors`
- `test_without_a_kept_model_a_broken_yaml_is_refused_as_before`
- `test_an_ai_model_with_a_prompt_file_is_kept_and_read_back_after_the_prompt_is_gone` (the first failure)
- `test_the_fallback_is_the_repositorys_and_never_runs_anything` (the second)
- `test_includes_are_settled_from_the_snapshot_never_the_disk` (the third: a glob include with a file added, a kept
  file deleted, a plain include deleted)
- `test_a_read_the_snapshot_does_not_hold_fails_the_fallback_never_reads_the_disk`
- `test_a_kept_file_altered_in_the_store_is_refused`
- `test_every_example_is_kept_and_read_back_from_its_snapshot_alone`
- `test_the_engine_keeps_the_model_it_takes`

And the four suites with rc 0 (unit; the four Playwright files; ruff; `demo_check`), no page test skipped.

## Size budget

400 net lines of code outside `tests/` and `docs/`.
