---
name: improve-model
description: Review an ergostat model as system dynamics would and propose specific YAML edits that improve its structure (missing stocks, outflows, delays, perceived values, converting auxiliaries), each with its reason and source. Use when asked to review, critique or improve an ergostat.yaml, or when `ergostat check` reports structure findings. Proposes only; never applies an edit without the owner's approval.
---

# Improve an ergostat model

You are reviewing a model (`ergostat.yaml` and the files it includes) the way a system dynamics
modeller would, for an owner who may be new to system dynamics. Your output is a short list of
proposed edits, each a specific YAML change with its reason in plain words. You do not change
the model yourself: the owner approves each edit first.

The guidelines you apply are `docs/MODELLING.md` (`ergostat help modelling`, or the MCP tool
`improve_model`, which returns this skill and the guidelines together). The format is
`docs/SPEC.md` (`ergostat help spec`, or the MCP tool `spec`). Read both before proposing anything.

## 1. Gather the evidence

Run these in the project (with the MCP server, the tools of the same names):

- `ergostat check` (MCP `check`): errors first (the model will not run until they are fixed),
  then findings. The structure findings are `rate-driven-by-rate`, `stock-without-outflow`,
  `outflow-ignores-stock`, `units-mismatch`, `auxiliary-without-causes` and
  `stock-without-flows`; each ends with its fix and the YAML that writes it.
- `ergostat residual` (or the Residuals page; MCP `findings` reports the significant ones): which
  stocks move more, or less, than their flows explain, and which way.
- `ergostat explain` (MCP `explain`): the feedback loops, each R, B or of unknown polarity, and
  any part in sentences (`ergostat explain flow.x`).
- Read the YAML itself, and the program behind any sensor whose meaning is unclear: what a stock
  counts is what its sensor reads.

## 2. Walk the checklist

For each item, note what you found and where (file and line):

1. Every structure finding: is the model wrong, or is it right and the check cannot know it?
2. Each stock: what fills it, what drains it, and does each drain depend on what is there?
3. Each `driven-by` on a flow: does the effect come at once? If not, where does the cause wait
   (a stock), and what ends its wait (the flows out of it)?
4. Each link: is it signed, and do its units convert?
5. Each decision: what does the decision maker actually see, and how late? (A perceived value is
   a stock.)
6. Each long delay between cause and effect: is the stock of what is in transit in the model?
7. Each significant residual: which flow or stock could explain it?
8. Each auxiliary: explained by the model, or declared as coming from outside (`exogenous: true`)?

Ask the owner (one short question) when only they can know: whether something really happens at
once, what a decision maker sees, whether a total ever drains.

## 3. Propose edits

For each problem worth fixing, propose one edit:

- **What**: the part, its file and line, and what is wrong in one sentence a newcomer can follow.
- **Why**: the system dynamics reason, and its source (the guideline in `docs/MODELLING.md`, and
  Sterman's chapter or Forrester).
- **Edit**: the exact YAML, before and after, ready to paste. Keep the model's own names and
  comments; add a short comment saying why where the next reader might disagree.
- **Measured how**: a new stock or flow needs a sensor that tells the truth. If its items have no
  state for it, say which events would give them one, and who would emit them.
- **What changes**: the loops it adds or removes, and whether the goals still close (`ergostat
  check` says how many goals are closed; that number must not fall without the owner's say).

Prefer the smallest edit that makes the structure true. Answer a finding without changing the
structure (`instant: true`, `cumulative: true`, `exogenous: true`) only when the model is right,
and say why in a comment. Never silence a finding to make `check` quiet.

Order the list by consequence: wrong structure first (missing stocks and delays change every loop
through them), then units and signs, then the rest. Say plainly what you left alone and why.

## 4. Apply only with approval

Show the list and stop. When the owner approves an edit (or a set), apply exactly that, then run
`ergostat check` again and report: the errors (none), the findings that went away, any new ones,
and the number of goals closed before and after. If an approved edit turns out to need more (a
sensor, an event the world must emit), say so before doing it.
