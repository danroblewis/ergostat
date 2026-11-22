# {branch}: simplify {module}

depends-on: []

Asked for by the simplifier (`dev/bin/simplify.py`, source: simplifier), which picked this module by its evidence
(score {score}). The evidence names candidates only: a "dead candidate" is a top-level name nothing else in the
repository names as a word, which a name built at run time (`getattr`, a table of names) would not show. Check each
one before you remove it.

## The area

`{module}`, and only what it needs changed with it (its callers, its tests).

```json
{evidence}
```

## The rules of a simplification

- Remove and simplify only, without changing behaviour: no new feature, no new option, no renamed command or field.
- Every test green: the unit suite and the four browser files, rc 0; ruff clean.
- No test deleted unless the code it tests is deleted with it.
- The branch removes more than it adds: its net lines over the whole diff (tests and docs aside) are below 0.
- One commit trailer per removal, in the commit that makes it:
  `Removed: <class> <path>[::<name>] <lines>`, where class is exactly one of `dead`, `duplicate`, `over-general`,
  `wrong-layer`, `speculative`, and lines is the net lines it removed. A removal that is none of these is not one
  this gap makes.

## Definition of done

1. The module is simpler by the evidence above: fewer net lines, and fewer of its duplicates, dead candidates or long
   functions, each removal with its trailer.
2. Behaviour unchanged: the existing tests of the module, unchanged but where their code went, are the acceptance tests.

## Acceptance tests

- The unit suite and the four browser files, rc 0, with no test deleted that still has code to test.
- `uv run ruff check ergostat tests scripts` clean.

## Size budget

0 net lines at most outside tests/, docs/ and dev/, and below 0 over the whole diff (tests and docs aside).
