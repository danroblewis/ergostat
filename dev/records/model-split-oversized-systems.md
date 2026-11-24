# model-split-oversized-systems: landing, times and intake become smaller systems

The modelling loop asked (four requests) because these systems are too large to redesign in one pass:
- `landing` has 45 parts in 3 clusters joined by 2 links: the merge queue and gaps, upgrade draining, and upgrade availability with the upgrader.
- `times` has more than 40 parts and no subsystems.
- `intake` has 2 clusters joined by 1 link, 131 times apart in time scale: open-gap dependencies, and join/split handling.

Change. In `dev/model/`, split each into named subsystems along those clusters. Change no equation, setpoint, limit or behavior: only which system a part belongs to. Every part keeps its id or is renamed with its references updated.

Definition of done.
1. `ergostat check` passes on the factory's model, with the same parts, flows and goals as before (a test compares them).
2. No system has more than 40 parts.
3. The Dynamics and Blocks diagrams render with the new systems (tests/test_diagram_rendering.py).
