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
