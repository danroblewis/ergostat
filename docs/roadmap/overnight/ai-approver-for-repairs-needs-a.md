# ai-approver-for-repairs-needs-a: the repair loop's second rung

Branch `factory/ai-approver-for-repairs-needs-a`, from main. Its definition of done is
`dev/records/ai-approver-for-repairs-needs-a.md`; this note is for people reading what was built.

`approver: ai` in `use: repair` is accepted by `check` again. After a fix passes its test, a guard in code
(`ergostat/repair/allow.py`) decides whether an AI may be asked at all. The earlier attempt, cut from `repair2`, denied
a list of dangerous calls and was bypassed many ways; this guard allows a list instead: changes that compute with plain
(JSON-type) values and print, and nothing those changes reach may do more. Anything it cannot read is a reason for a
person. When it may ask, the AI (haiku by default, no tools) sees only the program's path, the diff and "passed". Its
approval is stamped with the seqs and commit it judged and written only if that version is still the one waiting,
re-read under the failure's lock. The rest stays held for the person exactly as before.

What the guard does not see (implicit raises, where standard output goes, other modules, time and memory) is stated in
SPEC §12r and `docs/SECURITY.md`, each pinned by a test in `tests/test_repair_allow.py`. What is left is in
`docs/GAPS.md`.
