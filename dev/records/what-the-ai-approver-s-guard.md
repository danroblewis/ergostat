## Entry

section: Running code ergostat does not trust

- **What the AI approver's guard does not see** (SPEC §12r, `approver: ai`; the guard is an allowlist of shaped
  values and statements, `ergostat/repair/allow.py`). Its five residuals, each pinned by a test: implicit raises (a
  fix may stop the program earlier; process-wide hooks are not followed); where standard output points (a module the
  program imports may point it at code of its own); other modules' code (what an import does, and what another
  module's function does when called, such as `unittest.mock.patch('json.loads', f)`, `pickle` or a C extension);
  time and memory (bounded only by the timeout); the program's own unchanged code, which can rebind a builtin,
  `print` or `json` through a call the guard does not follow, or fill a shaped list or dict named to that call only
  as a string (`operator.attrgetter('paths')`; the refused spellings are a list, not a proof; a fix cannot add such
  a call). Trusting forms (a) to (c) only in a module whose every call is classified would close it, but would refuse
  nearly every real program (`open(...).read()` alone). A program that stores any attribute has no trusted `print` or
  `json` (bar `X.stdout = open(<constants>)`), so many real programs' fixes go to the person. Likewise a list or dict
  the program fills in place (`append`, `d['k'] = v`, even of shaped values) or hands to a call is not shaped, nor is
  anything aliased with it or taken from it, and a name reached as an attribute (`__main__.paths`) is read as that
  name; reading such fills as shaped bindings would let more through. A generator or an `enumerate`, `zip` or
  `reversed` iterator is shaped only where it is used up in the same expression (a `for`'s iterable, `list(...)`,
  `'-'.join(...)`), never held by a name, so a name holding one goes to the person. A `for` ended early by a
  changed, removed or controlled `break` or `return` must be over a shaped value, and its target is tainted, so a loop
  over `os.listdir(...)`, a parameter or a shared iterator that a fix ends early goes to the person. *Left*:
  `inbox/interventions.py` reads `stats.asked`, so an action the AI approved is still counted there as an
  intervention, as one answered through the MCP already is; a fix that calls one of the module's own functions always
  goes to the person (the plan's "pure function" form was dropped).
