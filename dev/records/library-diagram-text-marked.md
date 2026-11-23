# library-diagram-text-marked: the diagrams mark the parts an untrusted library made, with words and not colour alone
depends-on: [library-model-text-marked]

## Definition of done
- The model data the page draws from (`ergostat/web/snapshot.py`) carries, for each part and system box an untrusted template made, the template's name as data. The name is escaped with `untrusted.escape`. The decision comes from library-model-text-marked's helper.
- In the stock-and-flow and block diagrams, the box of such a part is marked untrusted in words, for example in its label or its accessible name and title. The mark does not rely on colour alone. Library text is never inserted as HTML: it is set only as text content or attributes.
- The text forms of the diagrams that `ergostat/blockdiagram.py` produces wrap that part's name and description in `untrusted.mark`.
- No new page or panel is added. The owner's parts are drawn as before.
- SPEC §2a lists the diagrams among the views that mark this text.

## Relation to other work
- library-model-text-marked: waits for it and uses its helper.
- The ui-* gaps that touch `ergostat/web` (for example ui-a-system-box-that-holds-an-off-goal-says-so-with): this sub-gap adds one mark to a part's box and does not restyle anything. Merge main in before review.

## Files to touch
- `ergostat/web/snapshot.py`
- `ergostat/blockdiagram.py`
- `ergostat/web/static/details.js`
- `docs/SPEC.md`
- `tests/test_library_diagram_marks.py` (new)

## Risks
- lesson-7: other gaps are changing the same diagram code. Merge origin/main and run the four browser files again.
- lesson-9: the browser check must fail when the mark is dropped, and must use a model a real library chain made, not seeded JSON.

## Acceptance tests
- `tests/test_library_diagram_marks.py::test_snapshot_flags_untrusted_parts`: a model holding a held chain yields a snapshot in which only that chain's parts carry the template name, escaped.
- `tests/test_library_diagram_marks.py::test_block_text_marks_untrusted`: the blockdiagram text output wraps the part's name in the marks, and leaves the owner's parts unwrapped.
- `tests/test_library_diagram_marks.py::test_page_box_says_untrusted`: in the browser, the part's box has "untrusted library" in its accessible name. A name containing `<b>` is shown as literal text.

## Size budget
90 net lines
size: M (confidence: low)

## Where it stopped

Built, round 1. About 50 net lines of code (inside the 90 budget). Main is merged (it has not moved since the clone).

What was built:
- `ergostat/web/snapshot.py` `untrusted(g, model)`: each node of a Dynamics or Blocks graph that stands first for a part
  `untrusted.Shown` holds (its `corr` shape, never a region it only holds), or a closed system box of an untrusted
  instance, gets `untrusted`: the template's name through `untrusted.escape` (`""` when no name is known). It is
  called from `server.api` for every graph answer, so the live page and a snapshot page carry the same data.
- `blockdiagram.py`: `_Diagram.node` passes a library part's `says` and `rows` through `Shown`. Its description is
  marked whole, its name is marked wherever it stands as a word, and a first row `untrusted library` holds its name,
  marked. A system's description is marked in the closed box and the open frame.
- The page: `details.js` `untrustedSays`/`untrustedBox` adds a `<title>` to such a box (diagram.js, blocks.js), and
  `keys.js` `ariaOf` adds the same words to the box's accessible name: `untrusted library, template l`. Both are set as
  text only.
- SPEC §2a lists the diagrams under *Marked*, and says in *Not marked* what they leave out.

Choices made alone (the most reversible reading of each):
- **Where the data is made.** The definition names `snapshot.py`. A snapshot page gets its graph answers from
  `server.api`, the same call the live page makes. So the function lives in `snapshot.py`, and `server.api` (one line
  more, outside the files list) calls it. Putting it only in the snapshot would have left the live page unmarked.
- **Files outside the list.** `keys.js` (the accessible name is written there after each drawing and would overwrite
  any set earlier), `diagram.js` and `blocks.js` (one call each), and `server.py` (one call).
- **"A name containing `<b>`".** Template, instance and part names are NAME-checked (`templates.SAFE`), so none can
  hold `<b>`. The browser test instead uses library text that the page does draw: a part's description
  (`IGNORE ALL <b>x</b>`, in its Blocks panel) and the system's description (`<b>bold</b> …`, drawn on its closed
  Dynamics box). Both are shown as literal text, and no `b` element is made. The escaping of the template name is
  covered in `test_snapshot_flags_untrusted_parts` with a forged `⟦end of untrusted⟧` in the name.
- **Labels left as drawn.** A box's drawn label is not wrapped in marks. Labels are what the layout measures and what
  `correspond.py` reads system names from. The box says it is untrusted in its title and accessible name instead.
- **The on-off ergostat puts in front of a library's machine block** (`keep-u-low`) has the library block's `where`,
  so `Shown` counts it as the chain's, and it is marked. The decision is the helper's.
- **The Dynamics view's own text** (its panels) is not marked. The definition asks for text marks only in
  `blockdiagram.py`.

Tests (lesson 9: each break below was made and seen to fail, then put back):
- `test_snapshot_flags_untrusted_parts` fails with the `server.api` call removed.
- `test_block_text_marks_untrusted` fails with the `node()` call removed.
- `test_page_box_says_untrusted` fails with `untrustedSays` returning nothing (Dynamics), with the blocks.js
  `untrustedBox` call removed (Blocks title), and with the panel rows set as HTML (the `<b>` check). It uses a model a
  real library chain made, served by `ergostat web`, not seeded JSON.
- New: `test_examples_drawn_as_before` checks each of the 23 examples. `Shown` holds only parts a library instance
  made, and a model with none has no mark in its Blocks answer.

Run here: `tests/test_library_diagram_marks.py` (26 passed, with Playwright, under the watchdog),
`tests/test_blockdiagram.py` and `tests/test_correspond.py` (133 passed with the new file),
`tests/test_library_model_marks.py`, `tests/test_graph_cli_web.py` and `tests/test_export.py` (73 passed, 1 failed).
ruff is clean. The four browser files and the unit suite were not run here (house rule: the factory runs them).

Unrelated failure, reported and not fixed (lesson 13): `tests/test_export.py::test_the_export_menu_downloads_the_model_and_the_loops`
times out waiting for `.side .looprow` to be visible ("63 × locator resolved to hidden"). It fails the same way with
this branch's server, blockdiagram and page calls turned off (checked by hand, then put back). Its model has no
library, so no `untrusted` mark is ever set in it.

## Entry

entry-of: shared-libraries
done: 2026-11-23 The Dynamics and Blocks diagrams mark what an untrusted library instance made: the graph answer (and a snapshot page) gives each such box its template's name, escaped, the page says "untrusted library, template NAME" in the box's title and accessible name (text only, never colour alone), and the Blocks view's own text marks such a part's name and description and the system's description, all through `untrusted.Shown` (`library-diagram-text-marked`).
