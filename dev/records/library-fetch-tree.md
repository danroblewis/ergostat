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
