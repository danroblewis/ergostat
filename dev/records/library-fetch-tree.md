# library-fetch-tree: `libraries:` entries checked by allowlist, and a library copy walked, extracted and hashed with symlinks hashed explicitly
depends-on: []

## Definition of done
This takes over `factory/library-fetch`'s `ergostat/library/sources.py`, `ergostat/library/tree.py` and `files.tree` (its record `dev/records/library-fetch.md`, rounds 1–3), trimmed to fit. Nothing here runs git or loads a library yet.
- `sources.py` checks a `libraries:` map (at most 16 entries, or `too-many-libraries`) with `re.fullmatch` allowlists for NAME, `git:` (https host/path or `file:///` only, with no userinfo, query or fragment), `version:` and `path:`. Anything refused is `bad-library-source`, naming the field.
- `files.tree` walks with lstat and never follows a link. It refuses FIFOs, sockets and devices without opening them, reads with `O_NOFOLLOW|O_NONBLOCK` and an `fstat` S_ISREG check, and stops at 2,000 entries and 20 MB.
- `tree.digest` hashes sorted paths with an explicit kind (`dir`, `file`, `exec`, `link`), followed by length-prefixed bytes or the link target. A changed link target or exec bit changes the hash.
- `tree.extract` reads a tar stream into a new folder. It refuses hardlinks, devices, absolute or `..` names, members under a link, and a link whose step-by-step walk leaves the copy or passes through another link. Names are compared case- and NFC-folded, and every link's realpath is checked once the links exist. Files are created `O_EXCL|O_NOFOLLOW`, under both caps, with declared and written bytes both counted.

## Relation to other work
- library-fetch-git and library-fetch-load: they build on this, and land after it.
- The parked branch `factory/library-fetch`: its code and tests are the source, cut down to these modules.

## Files to touch
- `ergostat/library/sources.py` (new)
- `ergostat/library/tree.py` (new)
- `ergostat/spec/files.py`
- `tests/test_library_tree.py` (new)

## Risks
- lesson-8: "links stay inside" must hold for chains through links and for case-insensitive disks, not only for a target's text.
- lesson-4: entry and byte caps on both the extracted and the walked copy, and declared sizes not trusted.
- lesson-3: an entry of an unknown kind is refused, never skipped.

## Acceptance tests
- `tests/test_library_tree.py::test_sources_allowlist`: `a\n`, `../x`, `ext::sh -c x`, `ssh://…`, userinfo, `http://`, `?q`, `--upload-pack=x`, `a..b`, `x@{1}`, `main\n` and `../up` are each refused. 17 entries are refused too.
- `tests/test_library_tree.py::test_link_and_exec_bit_change_hash`: retargeting a link, or `chmod +x` on a file, changes the digest.
- `tests/test_library_tree.py::test_extract_refuses_escaping_links`: `x/s -> ..` with `x/y -> s/../..` is refused in either order, as are `x/S`, the NFD variant and a member under a link.
- `tests/test_library_tree.py::test_caps_and_written_bytes`: small caps refuse. With declared sizes patched to 0, the bytes written still refuse.
- `tests/test_library_tree.py::test_fifo_refused_without_hanging`: a FIFO in the copy is refused within 20 s (run in a subprocess).

## Size budget
230 net lines
size: L (confidence: medium)

## Where it stopped

Round 1: built. All five acceptance tests pass, plus `test_not_read_while_replaying`. `tests/test_cli_fallback.py` (the existing users of `files.py`) passes too. ruff is clean.

The parked branch `factory/library-fetch` and its record are not in this clone, so the modules were written fresh to this definition, not cut down from that code. The choices made, each the more reversible one:
- `sources.check(map)` returns the checked map and raises `SourceError(code, field)`. `git` and `version` are required and `path` is optional. Any other key is refused, a value that is not a string is refused, and a version or path that begins with `-` or `.` is refused. The YAML key `libraries:` is not wired into loading, because that belongs to library-fetch-load. For the same reason SPEC and the agent guide are unchanged: nothing a user can reach yet.
- `files.tree` and `tree.extract` raise `files.TreeError` with code `bad-library-tree` or `library-too-big`. `files.tree` also refuses past `DEPTH` = 64 folders. That ceiling keeps the recursion and its open folder handles bounded (lesson-4). `files.tree` raises `NotKept` while a snapshot is replaying, because a library copy is not in the snapshot.
- `tree.extract` refuses a name that has a `.` or empty step, including a leading `./`. `git archive` writes none. On any refusal it removes `dest`, which only it created (it makes `dest` with `mkdir`, and the mkdir fails if `dest` exists). A tar or OS error is turned into `bad-library-tree`. A link whose step walk lands on any link, even as its last step, is refused.
- Checked by breaking the code (lesson-9), with each test seen to fail: dropping the re-walk after all links exist, dropping case folding, not counting written bytes, hashing exec as file, and opening a FIFO blocking without the lstat refusal (that one timed out at 20 s).

Left: nothing in this definition. library-fetch-git and library-fetch-load build on it.

Overrun reason: 257 net lines against 230 (tree.py 147, files.py +66, sources.py 44). The extra lines are fail-closed handling the definition's risks ask for: the folded parent check, the second link walk once all links exist, the folder-by-handle O_NOFOLLOW descent in both walk and extract, and the depth ceiling. The docstrings were already trimmed once.
