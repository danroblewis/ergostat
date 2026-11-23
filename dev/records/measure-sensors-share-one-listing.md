# measure-sensors-share-one-listing: the measure sensors stop starving the load sensors

Each `dev/bin/measure.py` reading calls `fac.items("gap")`, which lists every state through about 20 CLI calls (about 18 s). With about 95 such sensors on the engine's 8 sensor readers (`READERS`), the 15-second load sensors (`suites-running`, `suite-threads`, `suite-memory`) wait behind them and read as stale. Stale counts as off, so `queue-when` keeps the merge queue shut while approved work waits.

Change.
1. Measure sensors share one recent listing of a kind instead of each reading the whole record, or read it through one cheaper call.
2. A slow sensor cannot delay a fast one: short-interval sensors must not wait behind long-running readings.

Definition of done.
1. A test shows many slow sensors do not make a 15-second sensor stale.
2. A test shows concurrent measure readings of one kind make one listing within the sharing window.
3. A reading is never older than the stated window, and a failed listing is not cached.
4. Do not run load tests or measure the live instance in the session.
