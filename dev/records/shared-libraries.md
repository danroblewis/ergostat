## Entry

section: Remote systems and libraries

- **Shared libraries** (parked on `libraries`, `docs/roadmap/overnight/libraries.md`, *Where it stopped*): templates
  and reference models shared between projects and people, by git URL or package, with versions, bringing their own
  scripts. For people modelling their own real systems. **Unblocked on the sandbox side** (`sandbox`, SPEC §12q): an
  untrusted library's scripts can now run in the allowlist sandbox, with no reads of the owner's files and network
  only to hosts the owner lists. **Built** (`library-trust-folders`): a `library:` entry `{folder: PATH}` is untrusted
  unless it says `trust: owner`; its templates never shadow a trusted one; a use whose chain holds one may make only
  structure on an allowlist (`ergostat/library/trust.py`: no command, query, daemon, timer, machine block, agent,
  workspace, action or lease, and no block `out:` to a part the chain did not make, so none of the owner's machine
  blocks or setpoints is commanded by it; its parts may still read and name the owner's), or the whole chain is
  refused at the owner's `use:` line, with a refusal that suggests no copy into `with:` (SPEC §2a, SECURITY
  *Libraries you did not write*). **Built** (`library-untrusted-text`): an untrusted template's text is marked in the
  `templates` tool and in three kinds of `check` problem, its names checked, and its parts' schedules, pools,
  attempts and runs at once bounded at compile and when runs start, a second line behind the allowlist (SPEC §2a,
  *Untrusted libraries*). **Built** (`library-provenance-marks`): values carry their writer through expansion and
  nested uses, so a held chain may run the owner's own `type: command` values (whole, or quoted into a built-in's
  run) and pass only narrow, fully matched, bounded library values after data flags of ergostat's own programs
  (`LIB_DATA_FLAGS`, `--every` at the same 5-minute floor). An owner folder's run takes no library value, not even a
  quoted one (`sh -c ${x:quote}` runs whatever lands in it), which replaces the parent plan's "quoted library literal
  accepted in trusted text". **Built** (`library-provenance-join-1`, R3): a held chain's `ask`, `prompt`, sensor
  `query` and `sources` entries stand only when no piece of them is the library's (a piece whose writer can't be told
  counts as the library's, the instance's name and a part's renamed name included), else the use is refused as `untrusted-text`; `ai` and `person` blocks may say only that
  text, `goal`, `until`, `every` and `cron`, every other key refused by name (SPEC §2a, R3). **Built**
  (`library-sandbox-sensors-proven`): a sensor `run:` runs on the owner's shell only when compile proved it the owner's
  or ergostat's (an allowlist: `Sensor.run_in`, `ergostat/library/runs.py`); any other, a library's own script
  included, is no longer refused but runs only through `ergostat.sandbox` with no hosts, an empty environment, only its
  template folder readable, a work folder `<state>/library-work/<instance>` cleared when the chain above it changes, at
  most 120 s and 4 at once; with no sandbox nothing runs, and a library's sensor daemon is refused
  `library-unsandboxed` (SPEC §2a, *Sandboxed sensor runs*). Proven on the captured `Policy`; enforcement is the
  attack suite's. *Left*: library blocks in the sandbox (`library-sandbox-blocks`). **Built** (`library-fetch`):
  `libraries:` (main file, at most 16) fetched by git URL (https or file, every field on an allowlist) by
  `ergostat library fetch` into `.libraries/NAME`, under one flock across read, clone, swap and lock write, pinned in
  `libraries.lock` by commit and tree hash (a missing or altered copy is fetched again at the locked commit); each
  load checks the copy against the lock, refusing a lock entry without a tree, hashing symlinks explicitly by their
  target (never followed), and parses the bytes it hashed (SPEC §2a, *Libraries fetched by git URL*; SECURITY
  *Libraries you did not write*). A fetched library without `trust: owner` is untrusted exactly as an untrusted
  folder is: held, allowlisted, bounded and marked (`library-fetch-load`).
  *Still needed:* the text an untrusted template makes in the model marked too (its system's and parts'
  descriptions, prompts, commands, equations and names, wherever `check`, the diagrams and the MCP model views show
  them, and the `library-untrusted` refusal's folder path); `fetch` by package; a test that a fetched untrusted
  library's sensor run goes through the sandbox (it takes the same untrusted flag; not yet tested for a fetched copy);
  then running untrusted library blocks' scripts through `ergostat.sandbox` (its sensors' runs are built, above) and
  the rebase onto main.
