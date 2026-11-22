# Security: running programs you have not vouched for

Ergostat sometimes has to run a program nobody has checked yet: a fix an AI agent just wrote, run to see whether it
works before you approve it, or a script that came with a library someone shared. For those it has a sandbox
(`ergostat/sandbox/`, SPEC §12q). This page says, plainly, what that sandbox stops and what it does not. The repair
loop (`use: repair`, SPEC §12r) runs every fix it tests in it, on a throwaway copy of a clone with its own `.git`; its AI
has no tools at all and reads only the files ergostat gives it. Libraries do not use it yet (`docs/GAPS.md`).

**What a repair does not stop.** A fix you approve is merged into your repository and then runs
as the program it replaced did, with your rights and outside any sandbox. The sandbox only makes testing it safe before
you decide, and only within limits: a fix can tell it is in a sandbox (its home folder is unreadable, it has no DNS),
so a fix that behaves only when sandboxed passes. Read the diff before you approve: every notification of a repair
says so.

**What the AI approver does not stop** (`approver: ai`, SPEC §12r). An AI may approve a fix only when a guard in code
lets it be asked: the guard reads the program before and after and accepts only changes that compute with plain values
(strings, numbers, lists, dicts read from JSON) and print, and nothing those changes reach may open, run, import, write
or call anything else. A list or dict counts as plain only if nothing in your program fills it in place, hands it to a
call or keeps it where the guard cannot follow it, since that code could put anything in it. A generator or iterator
counts only where it is used up at once, never kept in a variable, since a fix that reads it would empty it for the
code after. A `break` or `return` the fix makes, removes or steers may end a loop early only over such a plain value,
and nothing after the loop may use its variable unchecked. Everything else goes to you, and so does every fix the AI does not approve. The guard says only
what the AI may be asked about; the AI can still approve a wrong fix within that. What the guard does not see:

- **Implicit errors.** Any lookup or division may raise, so a fix can make the program stop earlier, or get further
  than the failing program did (that is what a fix does). Only the old program's own statements then run, and a change
  near a `try` or `with` goes to you; hooks the program installs (`sys.excepthook`, `atexit`) are not followed.
- **Where output goes.** A fix's `print` writes to the program's standard output, or to a file the program opened by
  a constant name. A program that stores any attribute (its own `sys.stdout`, a replaced `write`) goes to you, but a
  module it imports can still point standard output at its own code, which then runs on what `print` is given.
- **Other files.** The guard reads one file. What the modules the program imports do, when imported or when the
  program calls them (say, `unittest.mock.patch` replacing `json.loads` or a builtin by name, or code loaded by
  `pickle`), is not seen.
- **Time and memory.** A fix may use a lot of either; the block's timeout bounds it.
- **The program's own code.** The guard trusts that `len`, `print`, `json.loads` and the like mean what Python gives
  them. It refuses a program that rebinds them in ways it can read, but your program's unchanged code could still
  rebind one through a call the guard does not follow (`operator.setitem` on a module's namespace, code run from a
  string), and the same kind of call could fill a list or dict it names only as a string. A fix cannot add such a
  call; the trust is in your committed code, not in the fix.

## What it stops

The sandbox works by **allowlist**: the program may touch only what is listed, and everything else is refused by the
operating system (macOS: `sandbox-exec`; Linux: `bwrap`). If neither is there, ergostat refuses to run the program at
all. It never falls back to running it unprotected.

- **Reading your secrets.** Your whole home folder is closed: SSH keys, `~/.netrc`, `~/.config`, cloud and API
  tokens, `~/.claude*`, shell history, browser profiles and cookies. So are other temporary files. On macOS the
  keychain cannot be asked either. The program can read only its own work copy, the language it runs in (Python and
  the system's libraries and tools), and folders the caller names.
- **Writing outside its folder.** It can write only in its work copy and a private temporary folder that is deleted
  afterwards. Not `/tmp`, not your home folder, not your other projects.
- **Changing git behind ergostat's back.** The program cannot write the work copy's git metadata at all, so it cannot
  plant a git setting (an `fsmonitor`, a filter, a hook, a signing program) that would run later outside the sandbox.
  Ergostat makes every commit itself, with git's dangerous settings switched off, and checks before each git command
  that the copy's git pointers are still the ones it made.
- **Sending your data out.** There is no network unless the caller lists hosts. Then the only way out is a proxy
  ergostat starts, which lets through only the listed host names, does the name lookups itself (the program can do
  none, so it cannot leak data through DNS), and logs every connection, allowed or not. It cannot reach other
  programs on your machine through local ports either.
- **Leaving something running.** Everything the program starts is killed when the run ends or times out, including
  processes that tried to detach (`nohup … &`, a new session, a double fork, a process that keeps forking itself to
  a new process id). If ever one cannot be killed, the run fails and says which.
- **Knowing it is being tested.** The program gets a short list of ordinary environment variables and what the caller
  passes on purpose: no `ERGOSTAT_…`, dry-run or test markers, and a temporary folder with an ordinary name.

Each of these is tested by an attack (`tests/test_sandbox_attacks.py`), with fake secrets in a fake home folder.

## What it does not stop

- **Reading other programs' command lines and environments (macOS).** Any of your own processes' arguments and
  environment variables can be read from inside: macOS's sandbox does not guard that kernel call
  (`kern.procargs2`) for the same user, and ergostat runs the program as you. The process list itself is denied, but
  process ids can be guessed. So a token you keep in an environment variable of a running program (a shell, an
  editor, an agent) can be read. Keep tokens in files, not in long-lived environments, until runs get a user of their
  own (which needs an administrator to set up). The attack suite records this as an expected failure. On Linux the
  run's own process namespace hides other processes.
- **Doing harm to a listed host.** If you list `api.example.com`, the program may send it anything that host accepts.
  Method limits (for example "GET only") are enforced for plain HTTP. For HTTPS the proxy cannot see inside the
  encryption, so a host limited to some methods gets no HTTPS connection at all, unless the caller says the limit may
  go unchecked there. List as few hosts as you can. The proxy checks the host the program connects to and the name in
  its TLS greeting, not what it asks for once inside: a listed host that serves many sites (a CDN) may be asked for
  another site by its `Host` header inside TLS (domain fronting), and a greeting whose real name is encrypted (ECH)
  shows the proxy only the outer name.
- **Damaging its own work copy.** It may change or delete anything in its copy (except `.git`). The copy should be a
  throwaway, which is how repair uses it.
- **Using what it can read.** It can read the toolchain and the folders named for it. Do not name a folder that holds
  secrets. Ergostat refuses to name `/` or the whole home folder.
- **Noticing the sandbox.** A program can still tell something is unusual: reading the home folder fails, there is no
  DNS, and its folder's path is whatever the caller chose. What it cannot find is a marker that says "test". A fix
  that behaves only when watched is still possible in principle; tests run against real inputs make that harder,
  not impossible.
- **Using all the CPU, memory or disk** while it runs. Only the time limit bounds it.
- **Other programs on your machine using the proxy.** While a run lasts, another local program of yours could connect
  to its port and reach the listed hosts. It cannot reach anything else through it.
- **Bugs in the operating system's sandbox**, or a process that escapes it through one. macOS's `sandbox-exec` is
  marked deprecated by Apple, though still shipped and used (Chrome and Claude Code use the same mechanism).
- **Linux**: the attack suite runs on both (in the dev container on Linux, `docs/DEVELOPMENT.md`); where the two
  sandboxes differ (DNS, the process list, other processes' environments, the toolchain's folders, the pid hopper)
  each test has a form of its own for each.
- **A known macOS kernel bug.** On macOS 15.5 a sandbox profile with a long list of filters in one rule (seen with a
  list of about twenty `sysctl` names) panics the kernel instead of being refused: the machine restarts. Ergostat's
  profile keeps every rule to five filters or fewer and allows sysctl reads with a single small deny, and a test holds
  it there. Do not add long lists to it.
- **Claude Code sessions** (AI blocks with `tools:` or `actions:`) use Claude Code's own sandbox, not this one: they can
  still read most of the machine (SPEC §12k, *Not enforced*).
- **What happens after you approve.** Once a fix is approved and merged, it runs as your code always does, with your
  permissions. The sandbox protects the time before anyone has looked.

## Libraries you did not write

A folder of templates someone else wrote can be listed in the main file as `library: [{folder: PATH}]` (SPEC §2a).
A map entry is **untrusted** unless it says `trust: owner`; a plain path, and `$ERGOSTAT_LIBRARY`, are yours and
trusted (`untrusted: true|false`, a YAML bool, may say the same as `trust:`). A map entry written wrong (another
key, no `folder:`, a `trust:` other than `owner` or `untrusted`, an `untrusted:` not a bool or disagreeing) is an
error and its folder is not read at all. Trust is decided for each file: a template file that lies inside any folder
listed untrusted (as listed, or with links resolved) is untrusted, even when a trusted folder that holds it, such as
its parent, also reaches it.

An untrusted template never takes the place of ergostat's own template or one of yours of the same name, whatever order
the folders are listed in; the check says which one it skipped. A use whose chain holds an untrusted template anywhere
(it, or a template it uses, at any depth) is **held**: everything made from the first untrusted template down,
including trusted and built-in templates it uses, is checked against an allowlist (`ergostat/library/trust.py`), as
expanded, with every parameter's value put in. If any part is not on it, the whole use is refused at your `use:` line
(`library-untrusted`), and nothing of it is in the model. What a held chain may make:

- **Sections:** `systems`, `items`, `parameters`, `auxiliaries`, `stocks`, `flows`, `goals`, `blocks`, `uses`, and
  `sources` only as below (a template cannot write `sources:` today; the gate would judge one if it could).
- **Block types:** `onoff`, `compare`, `proportional`, `limit`, `delay`, `schedule`, `lookup`, `select`, `expr`,
  `timer`, `counter`, `alarm`: computed by ergostat from their inputs. Also `program`, `ai` and `person` blocks, only
  as below.
- **Sensor keys:** `items`, `state`, `entering`, `leaving`, `where`, `over`, `measure`, `sum`, `changes`, `unit`,
  `description`: sensors that count items or read a stock's changes from the record ergostat keeps; `run`, on
  your shell only as below and otherwise sandboxed; and `query`, `every`, `cron`, `timeout`, `averages`, only as below.

Each section's keys are listed in trust.py, each with its reason; any other section, key, block type or shape of value
is refused, including daemons on sensors (`library-unsandboxed`), `external` and `judge` blocks, `on-stale`, an item kind's `lease`, a goal's
`owner`, and `inferred` or `formerly` anywhere. A test holds this list to trust.py's tables
(`tests/test_library_trust.py`).

**What runs.** Every value carries who wrote it: you (in your own file's `with:`), a trusted template (ergostat's or
one from your folders), or the library. Only two kinds of `run` (a sensor's, or a `program` block's) run on your
shell:

- **Your own commands.** A value you wrote for a `type: command` parameter, which reached the run whole (each nested
  use passing it wholly as `${p}`, to a `type: command` parameter again), as the whole `run`, or quoted (`:quote`,
  `:arg`) into one of ergostat's own templates' runs. Any library words around it (`${cmd} | sh`), a library default
  for a command, a library's literal that equals a command of yours, or your value for a parameter of another type
  (a `string`) is refused in a block's run, and makes a sensor's run sandboxed (below).
- **Ergostat's programs with checked arguments.** In a built-in template's run that starts `${lib} ` (the programs
  `python -m ergostat.library.run` runs), a value the library wrote may stand only directly after a flag listed in
  trust.py's `LIB_DATA_FLAGS` (data such as `--kind`, `--state`, `--every`, `--limit`; never `--run`, `--render`,
  `--command`, `--url`, `--header`, `--folder`, `--keep`, `--timeout`, `--max` or the AI programs' budgets), only
  for a parameter typed `name`, `duration`, `number`, `integer` or `bool`, and only when both the value and the text
  that lands fully match its type's pattern (no space or newline): name `[a-z][a-z0-9-]{0,63}`, duration
  `[0-9]{1,9}(\.[0-9]{1,6})?(ms|s|m|h|d|w)?`, number or integer `-?[0-9]{1,15}(\.[0-9]{1,9})?`, bool `true` or
  `false` (or the bare flag). `--every` is at least 300 s (the floor every untrusted part has), `--limit` at most
  100, `--stand-in` at most 3600 an hour (`LIB_BOUNDS`). A library's value of any other type never reaches a run, nor does any value of one in the run of
  a template from your own folders (no test can vouch for `sh -c ${x:quote}`), nor a run holding an element's or a
  list's field (`${it.run}`, whose writer can't be told).

**A library's own sensor run goes into the sandbox.** A sensor's `run` that is neither of these (the library's own
script, a command with library words around it) is not refused but runs only through the sandbox above, never on your
shell: no network, no environment (so it cannot call ergostat back or relay a message to you), nothing of yours
readable, only its template's folder and a work folder of its own (`<state>/library-work/<instance>`, emptied when the
templates above it change), at most 120 seconds and at most 4 such runs at once. Where no sandbox can start, it does
not run and records nothing. A library sensor's `daemon` stays refused (`library-unsandboxed`): a process kept
running is not sandboxed. Anything ergostat cannot prove is yours (an unknown origin, a check that fails) goes to the
sandbox too. What ergostat's own tests prove here is what the sandbox is asked to enforce (the policy handed to it);
that it enforces it is the attack suite's (`tests/test_sandbox_attacks.py`), with the limits in *What it does not
stop* above.

A sensor's or a program block's `every`, `cron`, `timeout` and `averages` stand only as you or a trusted template wrote
them; a library's (its own `poll: 1m`) is refused. Whoever wrote it, the period of a part made under an untrusted
template is still at least 5 minutes (SPEC §2a, *Untrusted libraries*). A program block may say nothing else but
`goal`, `in`, `out`, `role` and its words: `parse`, `max`, `pool`, `lease`, `agent`, `workspace`, `actions`, `network`
and the rest stay refused. Marks are made only by ergostat as it expands a template; a template or a value that holds
a mark's control characters is refused whole.

A template from your own folders is trusted, but its run still takes no value the library wrote, even quoted: `sh -c
${x:quote}` runs whatever lands in `x`, and nothing can vouch for that. An unquoted `${x}` of a `string` is refused
too. Only your own command, passed wholly, reaches such a run. (This replaces the earlier plan to accept a quoted
library literal in trusted text.)

**What is read or asked (R3).** A person block's `ask`, an ai block's `prompt`, a sensor's `query` (its `source:` and
every field, keys included) and every value of a `sources` entry stand only when no piece of them was written by the
library: your own value, a trusted template's words, or both. A library's literal, its default or its words around
your value (`"${q} and more"`) refuse the whole use as **`untrusted-text`**, whose message suggests no copy into
`with:` and does not quote the text. A piece whose writer can't be told counts as the library's: a value without a
mark, a whole value given with no writer, a field of a value (`${m.q}`), an `each:` element or a key made from a
value in a trusted template's own text, or a part it names there (renamed with the instance's name). The instance's
name holds the library's `uses:` key (`u-ignore-previous-instructions`), so a trusted template that uses `${name}`,
`${here}` or `${folder}` may put only your own pieces in these keys, and what it passes to a template it uses counts
as the library's. An `ai` or `person` block may say only its text, `goal`, `until`, and `every`
or `cron` as written by you or a trusted template; `model`, `run`, `parse`, `context`, `review`, `agent`, `workspace`,
`tools` and the rest stay refused by name (`library-untrusted`). R3 says who wrote the text, not what it says: a
library's template still decides that a block asking your text exists, and what it reads (`in:`), within the limits
above. Only these four keys are judged so; any other text of the chain that a session or a person is shown beside
them (the names and descriptions of its parts) may still be the library's.

A block's `out:` commands the block it names, and sets the goal it names. So a held chain's blocks may name in `out:`
only parts the chain made itself: an `out:` to one of your blocks (a `program` block that deploys, run on the
library's timer) or to your goal's setpoint is refused like any other part (`library-untrusted`), and so is an `out:`
that is not a reference.

What this does **not** stop:

- **What your command is run on.** A library that runs your command chooses the kinds, states, counts and periods it
  runs on (`--kind`, `--state`, `--every` within its bounds), so your command may run on items you did not mean.
- **An agent writing your `with:`.** A value in your own file's `with:` counts as yours, whoever typed it: an agent that
  copies a library's command there makes it your command.

- **Its words reaching agents.** An untrusted template's descriptions, `example:` and `reading:` are still shown to
  the AI agents that use the authoring tools, and may try to steer them. In the `templates` tool and in three kinds
  of `check` problem they are marked as the library's (SPEC §2a, *Untrusted libraries*), which tells an agent what
  they are but does not stop it reading them; the text of the parts a template makes is not marked.
- **What you trusted.** A path entry, or a map entry with `trust: owner`, is trusted wholesale: its templates may make
  anything, and may take the place of ergostat's own. Read a folder before you mark it so.
- **An agent that can write the main file.** It can mark a folder trusted, as you can. The agent guide tells agents
  never to, but nothing enforces it.
- **What its allowed parts name.** Its parts may still name yours in every other place: a block's `in:` or `goal:`, a
  flow's `from:` and `to:`, a goal's `stock:`, a `driven-by`, a part's `within:`. So it can read your parts, add a
  flow to your stock, and put its parts in your systems. If one of *your* machine blocks reads one of its blocks
  (`in: block.x`), that block commands yours, by your wiring. A raised `alarm` shows on the page and counts as an
  intervention, as any alarm does.

## The page from elsewhere

The page answers only requests addressed to `127.0.0.1:PORT` on this machine. Behind a cloudflared tunnel it answers a
public name only when the model declares it with a Cloudflare Access login (`web:`, SPEC §4d; the how-to is
AGENT-GUIDE §3j): every request there, reads included, needs a valid Access token for an allowed email, writes are
recorded as that email, and the state directory's files (the push and remote tokens) are never served there. Any
request that came through Cloudflare without that declaration is refused, even one whose Host the tunnel rewrote.
A name declared `open: read` instead is public: anyone who reaches it reads everything the page shows, though nothing
can be written there. What it does not stop: anyone on the allowlist can read everything the page shows, and an allowlisted account taken
over is the owner on the page.
