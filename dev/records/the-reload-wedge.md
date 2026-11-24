## Entry

section: Done recently

- **The reload wedge**: the item index read under its lock; a reload waits for edits to settle, never takes a broken
  model and swaps atomically; a watchdog recovers a stalled pool, loop or process (merged from `reloadfix`).
