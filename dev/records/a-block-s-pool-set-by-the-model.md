## Entry

section: The factory (ergostat on ergostat)

- **A block's pool set by the model's state** (done, on `a-block-s-pool-set-by-the-model`; SPEC §9.5): `pool: {now:
  stock.NAME, most: N}` reads the block's pool from a measured stock at each dispatch, under the dispatcher's lock,
  rounded down and held within 0 and its most; no reading takes nothing new; a lowered stock drains. The completion
  estimates and the Blocks view read the pool now (1, said, when it is 0 or unread). The factory's implementor and
  reviewer take theirs from `implementor-pool` and `reviewer-pool`. Not done: an age limit on the stock's reading (the
  newest is used whatever its age), and a global ceiling on `pool:` numbers.
