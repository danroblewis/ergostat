# BRANCH: one line on what the gap is

depends-on: []

(The line above names the gaps this one waits on, by branch or gap id, e.g. `depends-on: [remote-systems, warm]`; the
factory builds it only once each is merged, and draws the tree. Leave it `[]` when it waits on nothing.)

Branch `BRANCH`, from main. Where the gap came from (its GAPS.md entry, or who asked), and why now.

## Definition of done

One paragraph: what is true when this is done, said so a reviewer can check it.

## Acceptance tests

- `tests/test_x.py::test_name`: what it shows.

## Size budget

600 net lines of code outside `tests/` and `docs/` (an overrun needs a written reason here).
