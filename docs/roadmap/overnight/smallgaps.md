# smallgaps: four small gaps, in order

Branch `smallgaps`, from main at 448f546. One commit per item, each with its test. Gaps from `docs/GAPS.md`.

## 1. The Blocks diagram crashes on a stock with no flows (bug)

**Done when** a stock that a goal holds but that no flow fills or drains is drawn in the Blocks view as an
integrator with no inputs (no summing junction, no `IndexError` at `blockdiagram.py:814`), in every view (all,
each system open, each system alone), and every example's Blocks view still renders.

Acceptance: `tests/test_blockdiagram.py::test_a_stock_with_no_flows_is_an_integrator_with_no_inputs_in_every_view`
(fails on main); `tests/test_blockdiagram.py::test_every_view_has_a_function_in_every_block_signs_at_every_junction_and_no_placeholder`
and `tests/test_diagram_rendering.py` still pass.

## 2. Light theme: the repeats toward the paper are low in contrast

**Done when** every correspondence colour in the light theme, each hue and its repeats toward the ink and toward the
paper (colours.js's `color-mix` in oklab, `--g-fade` of the hue), stands at least 3:1 on the light paper, as gapsfix
made the dark theme's; the hues keep their order and their OKLCH hue angle (only lightness, and chroma where the
gamut asks, change), and each hex says the OKLCH it was made from. Screenshots of a page with the correspondence
colours on, light theme, in `~/ergostat-wt/smallgaps-shots/`.

Acceptance: `tests/test_style_tokens.py::test_light_theme_correspondence_colours_stand_3_to_1_on_the_paper` (fails
on main: gold 2.4:1, its repeat 1.6:1); the dark theme's test still passes.

## 3. Per-item and per-group goals

**Done when** a goal on a stock counted from items (an `items:` sensor) may say `per:`: `item` (each item the sensor
counts is held to the setpoint by its own measure, its hours in its state for `measure: oldest`, since first seen
for `age`) or a field (a relation such as `parent`, or any field: the items grouped by the value, or each id, it
holds; each group's count, oldest or age held to the setpoint). The goal's value is the worst item's or group's; it
is off while any breaks the setpoint (its tolerance as usual), and its `loop.off` names the items or groups that
break it. The snapshot (`loops[NAME].breaking`), the loop's panel and "needs attention" list them (each with its
value), at any moment the page travels to. `check` refuses `per:` on a goal not on such a stock, and `per: item` with
`measure: count`. SPEC §8 and the agent guide say so. No new page or panel.

Acceptance (`tests/test_goal_per.py`):
`test_a_per_item_goal_goes_off_naming_the_items_older_than_its_setpoint`,
`test_a_per_group_goal_holds_each_parents_open_items`,
`test_per_needs_a_stock_counted_from_items`,
`test_needs_attention_and_the_loop_name_the_items_that_break_it`.

## 4. Relations, what is left

**Done when** the Process view draws the relations between the items it draws: a dotted line from an activity of
one kind to an activity of another (each linked pair at the activity each item was last at in the window),
aggregated, named by the relation, with how many links; its panel says what it is; the legend has it; `check`'s
coherence is unchanged by it. ticket-factory records Jira's links only if its collector already reads them (it
does not: `jira.py` asks for summary, status, labels and description); that, time travel for the Graph and
Timeline, and resource levelling are left, and noted in GAPS.

Acceptance: `tests/test_process.py::test_relations_between_the_items_drawn_are_lines_between_their_activities`;
`tests/test_diagram_rendering.py` (the roadmap example's Process view, which has relations) still passes.

## Size budget

600 net lines of code outside `tests/` and `docs/`, for all four together.

## Suites

`uv run python -m pytest -q`; the four Playwright files with no skips; `uv run ruff check ergostat tests scripts`;
`demo_check.py` for the examples touched (none expected; `roadmap` and `ticket-factory` checked).
