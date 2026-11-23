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

## Where it stopped

Built, round 1. What is in the branch:
- Change 1: `dev/bin/listing.py`. Run by the engine (`ERGOSTAT_STATE_DIR` set), `measure.py`'s listings of a kind go through `listing.items`. The first reading of a kind lists it (`fac.items`) while holding that kind's `flock` in `<state>/listings/`, and keeps the listing stamped with when the listing began. A reading that arrives within `SHARE` (120 s) of that start reads the kept listing. One that is older, from the future, has a stamp that is not a number, or cannot be read is listed again. A listing that fails raises and keeps nothing. With no state folder (in tests, or by hand) nothing is shared, as before.
- Change 2: `engine.lane`. A sensor read every 60 s or more often (`FAST`) whose timeout is 60 s or less reads on a fast pool of its own: 4 threads, fixed in `LANES` (8 + 2 + 4 = 14 reading threads at most). The watchdog watches the fast pool as it does the sensors' and the alarms' pools. A cron schedule, or an interval or timeout that is not a finite number, uses the slow lane.
- Acceptance: `tests/test_measure_sharing.py`. Done 1 is `test_many_slow_sensors_do_not_make_a_15_second_sensor_stale`: 12 slow readings are held open by a gate file and the 15 s sensor's reading comes back within its interval while every one of them is still out. Done 2 is `test_concurrent_measure_readings_of_one_kind_make_one_listing`: six `measure.py` processes run at once and make one listing. Done 3 is covered by `test_a_listing_is_shared_within_the_window_and_listed_again_past_it`, `test_the_age_counts_from_when_the_listing_began_not_when_it_ended`, `test_a_failed_listing_is_not_kept` and `test_a_failed_measure_listing_is_listed_again_by_the_next_reading`. Each one was seen to fail with its code broken: the lane always slow, the lock removed, the age check removed, a failed listing kept as empty.
- Choices made without anyone to ask, each easy to change back: the window is 120 s; `FAST` is 60 s; the fast lane has 4 threads; a fast sensor is chosen by both its interval and its timeout, so a short-interval reading that may run long stays on the slow lane; a sensor is not sorted by measuring how long its readings take. The "one cheaper call" option was not taken.
- Not run here (done item 4): no load test, and nothing measured on the live instance. Whether `queue-when` now opens on the live instance is unmeasured.
