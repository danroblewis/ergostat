# split-children-keep-parent-dependencies: a split's first part inherits what its parent was waiting on

Found 2026-11-23: `analysis-source-and-window-guard` depended on `result-frames-and-verdicts`. The groomer split it, the second child depended on the first, but the first child had no dependencies at all, so a planner started it while its prerequisite was unbuilt. The same happened to `observe-a-work-daemon-without-running-it-1`.

Change. In `dev/bin/backlog.py`, when a gap is split, each child with no dependency on a sibling takes the parent's unfinished `depends_on`, and the children's definitions carry it, so intake does not drop it. A split must never make work runnable that was blocked before.

Definition of done.
1. A parent with an unfinished dependency, split in two: the first child waits on it, and the second waits on the first.
2. A parent with a finished dependency gives none to its children.
3. A dependency survives intake re-reading the child's definition.
4. A proposal naming explicit dependencies for a child keeps them, plus the parent's.
