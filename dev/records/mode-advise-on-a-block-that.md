## Entry

section: The factory (ergostat on ergostat)

- **`mode: advise` on a block that takes items did nothing** (done on `mode-advise-on-a-block-that`; found by
  `factory`): the dispatcher (`ergostat/leases/dispatch.py`) leases items to a block whatever its `mode`; only
  commanded and event-started blocks ask. Of the two ways out, the refusal was chosen: `check` now refuses
  `mode: advise` with `takes:` (`advise-with-takes`, `ergostat/leases/compile.py::check`), saying to gate the block
  with `goal:` or `in: block.X` instead, as the factory pauses its implementor (the auxiliary `intake-open`, read by
  hand, in an `expr` that commands it). Asking once per item before it is leased (`block.advised` naming the item) is
  left unbuilt; the dispatcher and the inbox are unchanged, so an `advise:BLOCK` in the inbox never names a block
  that takes items only because `check` refuses that model. Tests: `tests/test_leases.py`
  (`test_mode_advise_on_a_block_that_takes_is_refused`, `..._without_takes_and_takes_without_advise_compile`,
  `test_a_block_that_takes_waits_while_what_commands_it_is_off`).
