## Entry

section: Interface

- **Searching items and querying their graph** (done, both halves merged; `gap/item-search`): full-text search and
  graph queries over items, from the CLI and API.
  - *Search*: **done** on `factory/item-text-search` (merged in `512f08ef`; SPEC §5a, *Search*): `ergostat item
    --search WORDS` and `/api/items?search=WORDS` list the items whose fields' text contains every word (a casefolded
    substring, no ranking, no fuzzy match; the first 65,536 characters of each item's text), kept in the item index.
    Not the Items page's own box, not MCP, not `--at`.
  - *near, path and about*: **done** on `factory/item-graph-queries` (gap/item-graph-queries; merged in
    `c5eb54e6`; SPEC §5a *Graph queries*): `ergostat item ID --near [N]`, `item A --path B`, `item ID --about`
    and `/api/items-query`: the items within N hops (1 to 4), a shortest chain of relations (a backward step named by
    its inverse), and what links to an item (`declared`) or names its id as a whole token in a field (`inferred`);
    each visits at most 2,000 items and says `capped` past that; an unknown id is an error. `--about`'s mentions are
    the items the index's text holds the id in (its first 65,536 characters), checked as a whole token in each string
    value of their fields.
