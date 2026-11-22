# blocks-subsystems-classified-c-p: Blocks: subsystems are classified C, P or a named block, with the same letter and dimensions at both levels

depends-on: [blocks-textbook-levels-proposal]

Problem (R4 piece 3): every closed subsystem is 'Q_name p x m'; Q is undefined in the legend and becomes P with different dimensions when opened, because the disturbance is counted at one level and not the other (shots/story-7-h1-blocks.png, story-7-h2-into-api-blocks.png, ce-sf-blocks-factory.png).
Change, as the proposal settles: ergostat/blockdiagram.py classifies each subsystem node from what it holds (controllers acting on another system's process: C; processes acted on from outside: P; both or neither: its own name as a named block) and counts inputs and outputs, disturbances included, the same way at the level above and inside; the node carries {letter, p, m} and its ports in a stated order (references, outputs, disturbances) that later gaps print on. blocks.js draws the letter with the system's name as subscript and p x m; the legend (filed Q68) defines the letter and p x m. Q is removed everywhere.
Definition of done:
1. On :8796, :8797 and :8791 no block is labelled Q.
2. For every subsystem the letter and p x m printed on the closed block equal those in the frame title when opened (a test walks every system of every demo).
3. The legend defines C, P and p x m.
4. Render tests pass.
Files: ergostat/blockdiagram.py, ergostat/web/static/blocks.js, tests (a blockdiagram unit test of classification on a small spec; tests/test_diagram_rendering.py).
Acceptance tests: unit: a system holding only controllers is C, only processes P, mixed named; the both-levels walk on the six demos.
Budget: 110 net lines.

Milestone: r4-blocks-textbook. Owner items: R4 piece 3. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 14:22).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 14:22).

Its runs failed past their attempts (a dead letter):
- attempt 1: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 2: nack given back
- attempt 3: nack exited 1
- attempt 4: nack the run ended with gap/blocks-subsystems-classified-c-p still parked
