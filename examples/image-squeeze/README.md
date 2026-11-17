# squeeze: a service, and a lab that optimises it

**squeeze** compresses the images customers send (photos, big photos, grayscale photos,
screenshots, line art, logos with transparent backgrounds) so they cost fewer bytes to serve and
still look as good. A **lab** of AI agents (Claude Code sessions, or free stand-ins) keeps proposing
changes to its code. Each change is tested on live traffic against the current version, on the
same images, and kept only if it measurably saves bytes at equal quality without breaking anything.

Nothing here needs people to judge it. Every image served is measured: its size, and how close it
looks to the original (SSIM, 1.0 identical, judged on white so transparency counts, and at full
size so shrinking counts as lost detail). The images are drawn procedurally (`world/images.py`), so
it runs anywhere with Pillow and numpy (`bin/py` finds a Python that has them, or asks `uv` for one).

## Run it

Work on a copy: it writes squeeze's repository, production and the candidate into `run/`.

```bash
cp -r examples/image-squeeze /tmp/squeeze && cd /tmp/squeeze
ergostat run                      # stand-in researcher and developer: free, a few minutes per experiment
FACTORY_AI=claude ergostat run    # Claude Code sessions propose (Sonnet) and write (Haiku) the experiments: real tokens
FACTORY_LIE=1 ergostat run        # a planted lying developer: its claims are checked, and caught
```

To start over: stop it, then `ergostat reset --yes` (forgets ergostat's record of it: events, items,
measurements, logs) and `rm -rf run` (squeeze's repository, production and the world).

Then the page `ergostat run` prints, or:

```bash
ergostat loop                     # the goals: holding or off
ergostat item --kind case         # the benchmark: which of the thirty cases squeeze meets, and how well
ergostat item --kind hypothesis   # every experiment, its state, and (ergostat item hypothesis/3) what it measured
ergostat explain small-images     # the whole chain, from the researcher to the bytes served
ergostat run --stop
```

## Where to look

- **The Diagram, every system closed** (the ⋯ menu's "Close all systems"): the control panel. Each system's box shows its
  measures, each with its value, setpoint, health and trend over the window (the window, top
  right, sets how far back): `service` (quality, bytes per megapixel, failures, time), `benchmark`
  (capabilities: cases met of 30; the benchmark points, overall, photos and flat images), `lab` (ideas,
  experiments, improvements, AI spend), `rollout` (the running experiment). Click a measure for its
  history; open a box (▸) to see how it works inside.
- **Items → `case`**: the benchmark as a gallery, each case's original beside what production makes
  of it now, its size against its target, met or not.
- **Items → `hypothesis`**: every idea, its state, and on its page what it is, what it measured,
  why it was kept or dropped, and examples (the original, production's output, the candidate's).
- **Items → `session`** (with `FACTORY_AI=claude`): every Claude Code session, its cost, and the
  path of its full transcript. ergostat records each line of the transcript as an event about the
  session as it runs (`claude.message`, `claude.tool-use`, ...), and the session's kind folds them into
  its conversation (`fold:` in `lab.yaml`): its page lists what was said, each tool called and what came
  back, and the tokens, each with its history.
- `run/product`: squeeze's own repository; every kept experiment is a merge (`git -C run/product
  log --graph`).
- **Items → `ergostat.claim`**: what the developer said it did ("tests pass", "submitted hypothesis/3"),
  each checked by ergostat after its run: verified, contradicted (with the evidence: squeeze's tests run again
  on the hypothesis's branch, the hypothesis's state) or unchecked; and under them, **Trust**, how far each
  block's (and each model's) claims held. The lab's `developer-honest` goal holds the developer's share
  contradicted at 0.1 or less (`ergostat.trust.contradicted@developer`). With `FACTORY_LIE=1` the stand-in
  plants a failing test on every other hypothesis, runs the tests through `tail` (so the pipe says they
  passed), and claims they passed and that it submitted: both claims are contradicted, the goal goes off, and
  the developer needs attention. `docs/CLAIMS.md` in ergostat says how it works.

## Three loops, fastest first

**1. The quality loop (seconds): regulation that optimises.** Every image is compressed at one encoder
quality, `quality-setting`. The `tuner` holds the measured `quality` (the 10th percentile SSIM: nine
images in ten look at least this good) at 0.93 by moving the setting by the error each time
(integral control: it settles on the setpoint, whatever the mix). Holding quality *at* the floor,
not above it, is what keeps bytes down: better than the floor costs bytes nobody asked for. The mix
of images shifts every four minutes (`flat-share`, set by the `customers`): that is the disturbance
the loop rides through. (An average would not do: screenshots look perfect at any setting, and
would hide photos turning to mush.)

A knob cannot fix a defect. squeeze starts out turning every transparent logo's background black
(JPEG has no transparency), so while logos arrive, no quality setting reaches the floor: the tuner
runs to the top of its range and stays there (saturated), the loop is off, and every image costs
the bytes of the highest quality. That is when the lab matters.

**2. The rollout loop (minutes): progressive delivery as feedback.** One experiment at a time, the
`candidate` build runs on the same images as production. Two controllers:

- the `matcher` holds `quality-change` (candidate minus production) at 0 by raising the candidate's
  quality setting (`candidate-offset`) when it looks worse: a tracking loop. A change that saves
  bytes by looking worse (WebP, blurring) is so compared at equal quality. A change that looks
  better is not made to look worse to match (its gain may be all on one kind of image, and
  spending it would make every other kind worse): it is kept if it looks better for about the same
  bytes, and the quality loop then turns production's setting down by itself;
- the `rollout` reads `bytes-saved` (a 90% confidence interval over the images both builds saw)
  and the images compared (`paired`). While the candidate is better, it gets more of the traffic
  (5%, 25%, 50%, 100%: `rollout-share`, and what is served moves with it), one stage per 30 images,
  and none while the service's own goals (`no-failures`, `fast-enough`) are off; then it is kept,
  merged, and production runs at its matched quality (`adopted`);
- the `rollback` holds the candidate to its guards, `candidate-sound` (no failures) and
  `candidate-fast` (120 ms at the 95th percentile, the budget written there), and drops it when it
  fails one, saves no bytes at equal quality, is much worse for some kind of image, loses a
  benchmark case, or shows no difference after 240 images. The rollout steps its traffic back, the
  matcher its offset.

This is what makes an AI developer's mistakes safe: a broken change shows up as measured failures
on a small share of traffic, and the loop pulls it back. Nobody has to notice.

**3. The research loop (hours, here minutes): the experiments.** Hypotheses are items
(`hypothesis/3`: proposed → building → testing → kept or dropped). The `researcher` proposes while
fewer than two wait (`ideas-ready`); the `developer` builds the oldest whenever the candidate slot
is empty (`one-running`). `small-images` (bytes per megapixel served ≤ 20) is the target the whole
lab chases: `ergostat explain small-images` traces it from the researcher, through the ideas and the
experiment, to the release kept, the benchmark points it gains and the bytes served.

## The fourth loop: the model of all this (model.yaml)

The model itself is kept true by a loop of its own (ergostat's SPEC §12e). Its fit to the record is measured
like anything else: `model-error` is ergostat's built-in measure `ergostat.model.fit`, the scaled error of the
model's replay, and the goal `model-fits` holds it at 0.02. While it is off, the `improver` (an `ai` block:
with `FACTORY_AI=claude` a Claude Code session on Sonnet with ergostat's tools, `prompts/improver.md`, which
reads the model, the code and the record and changes no file; otherwise a free stand-in) proposes changes with
their evidence. Every change to the model, the improver's and ergostat's own calibrations and structural
proposals alike, is an item, `ergostat.model-change/…` (Items → `ergostat.model-change`, and the review queue
on the Fit page, each with who made it, its reasons and their evidence): made → checked → testing → passed →
accepted, or refused, failed, dismissed, superseded.

The `judge` is a built-in block: it replays each change beside the model as it is on the four minutes of record
after it was made, whole, in halves and in quarters, and passes it only when the scaled error falls by 2% in
every window. A passed change to a parameter's value is written into the YAML at once (`accept: {parameter:
auto}`), and recorded as `ergostat.model.changed` with its diff and the fit before and after; a change to the
structure waits in the review queue. Commit what was written. The stand-in proposes what ergostat's calibration
declined to (an estimate within two standard errors of the value written): the judge, not the stand-in,
decides. Each improver run is a session item with its cost (0 for the stand-in).

## The benchmark: what squeeze can do

Bytes served depend on what customers happen to send. How good squeeze *is* does not: thirty fixed
images (five of each kind) are the benchmark (`world/benchmark.py`), each a **case** with a target,
the kilobytes per megapixel it should need while still looking good enough (SSIM 0.93; the quality
setting is searched, so it measures the code, not the setting). Like recorded signals a radio must
decode, they are not tests that pass or fail but a count of what the product can do:

- each case is an item (`case/logo-3`: met or unmet, its size now and its best so far): the Items
  tab's `case` table is squeeze's scoreboard;
- **`capabilities`** is the stock of cases met, filled by `gained` (driven by releases) and drained by
  `lost` (a disturbance); the goal `every-case` is all thirty (the noisiest photos may stay out of reach);
- **`benchmark-points`** is how good squeeze is now, in one number: the percentage fewer kilobytes
  per megapixel all thirty need than squeeze as handed over needed (so higher is better, and the
  seed is 0; the KB/MP themselves are in `run/world/benchmark.json` and in each case). It is a stock:
  it keeps its value until a release changes the code. What releases do to it are its flows,
  `benchmark-points-gained` (driven by kept hypotheses) and `benchmark-points-lost` (to outside: a
  release that breaks something; the rollback refuses one that loses a case, so nothing drives it), each measured from the points' own
  rises and falls (`changes:`), so a sudden drop shows as a large outflow. `photo-points` and
  `flat-points` are the same on the fifteen photos and the fifteen flat images;
- the points' sensor runs the benchmark once per release (and records each case it measured, as
  an observation: it measures, it never sets anything); every candidate is measured when it is
  submitted, and rolled back if it loses a case production meets (a regression no amount of live
  traffic in one hour might show).

squeeze as handed over meets 2 of the 30; the transparency fix and the encoder's optimisation take
it to about 9; screenshots, line art and logos need a flat-image policy that does not break
grayscale photos; the noisy photos need something better than any idea in the stand-in's notebook.

## Stocks and auxiliaries: sorted by memory

The rule: does it keep its value when nothing happens, and change only through some process? Then
it is a **stock**, and its changes are flows. Otherwise it is an **auxiliary** (`auxiliaries:`), a
momentary function of other things.

| Part | Kind | Why | Its flows |
|---|---|---|---|
| `quality-setting` | stock | stays where the tuner last stepped it | `quality-steps` (two-way, the tuner), `adopted` (a kept candidate's offset) |
| `candidate-offset` | stock | stays where the matcher last stepped it | `offset-steps` (two-way, the matcher's, back to 0 for each new candidate), out by `adopted` |
| `rollout-share` | stock | stays at its stage until the rollout steps it | `share-steps` (two-way, the rollout's, back to 0 once the candidate is decided) |
| `ideas`, `building`, `experiments`, `improvements` | stocks | hypotheses in each state: an aging chain | `started` follows the ideas waiting, `submitted` what is built, `kept` what is tested |
| `paired`, `candidate-failures` | stocks | counts since the candidate started | `compared` (while a candidate runs), `candidate-failing` (the build's own); `cleared` on a verdict, `failures-cleared` on a drop |
| `ai-spend` | stock | only grows, by each session's cost | `spending`, driven by the sessions running |
| `benchmark-points`, `photo-points`, `flat-points` | stocks | keep their value until a release | `-gained` (driven by kept) and `-lost` (a disturbance) |
| `quality`, `bytes-per-mp`, `failures`, `time` | stocks | each a window of the last 48 images served: system dynamics' first-order smoothing | one two-way turnover each, (the batch − the window) / the window's length, measured from its own net change |
| `batch-quality`, `batch-bytes`, `batch-failures`, `batch-time` | auxiliaries | what the ten images just served have, a momentary quantity: what the windows smooth | driven by the setting (+), the code kept as the benchmark measures it (+ quality, − bytes) and the candidate's share |
| `candidate-time` | stock | a window of the images compared | its turnover, filling while a candidate runs |
| `bytes-saved`, `quality-change` | auxiliaries | each is a difference between two builds on the same images, a function of what both did and of the offset | |
| `flat-share` | auxiliary, `exogenous` | a function of the clock, from outside the model: the customers' mix (its effect has no one sign, so unsigned) | |

So the tuner is an integral controller in the plain sense: it steps a stock (the setting) by the
error, and the stock's memory is the integral; `ergostat explain quality-held` names the roles.

### The feedback loops

Every influence carries a sign where the code justifies one, so `ergostat explain` can say which
loops balance and which reinforce:

| Loop | | What it does |
|---|---|---|
| `quality-held` | B | quality low → the tuner raises the setting → the batch looks better → quality rises |
| `matched` | B | the candidate looks worse → the matcher raises its offset → it looks better |
| `no-failures`, `fast-enough` | B | the candidate's traffic raises what is served's failures and time → while a goal is off, the rollout gives it no more |
| `candidate-sound`, `candidate-fast` | B | a failing (or slow) candidate is dropped → its failures are cleared (its window empties) |
| `ideas-ready` | B | ideas short → the researcher proposes |
| `one-running`, `one-running-3` | B | no experiment → the developer starts and submits one |
| `small-images`, `every-case` | B | the research loop: bytes over target (or cases short) → ideas → experiments → kept → benchmark points (cases) → fewer bytes |
| `quality-held+small-images` | B | the two together: better code looks better, the tuner turns the setting down, bytes fall |
| `one-running-2` | R | a developer that abandons builds leaves the slot empty, and keeps building |
| `quality`, `bytes-per-mp`, `failures`, `time`, `ideas`, `building`, `experiments` | B | each window adjusting to its batch, each stage of the chain draining |

The loops through the rollout's and the rollback's readings of `paired` and `bytes-saved` are of
unknown polarity until ergostat can be told which way a program block takes a reading.

## What the experiments find

The stand-in researcher works through a notebook (`bin/ideas.py`) of eleven ideas, each with the
code the stand-in developer writes for it. They are not all good, and the measurement decides. One
run of about 18 minutes went like this (the numbers move from run to run, with the mix of images
during each experiment and the order things are kept in):

| Hypothesis | Verdict | Why |
|---|---|---|
| Transparent images on white | kept | better looking (+0.17 SSIM) for the same bytes |
| JPEG optimised tables, progressive | kept | 21% to 28% fewer bytes at equal quality |
| Palette PNG for flat images | dropped | grayscale photos also count as "256 colours or fewer", and came out 14 times larger: the guardrail on each kind of image |
| Keep grayscale grayscale | dropped | 1.5% to 5% more bytes at equal quality |
| WebP for photos | dropped | to look as good it needed a higher quality (+14), and then photos were half as big again |
| Strip metadata | dropped | nothing to strip: no difference, slightly worse |
| Shrink anything over 1200 px | kept | 2% to 24% fewer bytes (judged at full size, the detail lost was small) |
| Soften photo noise | dropped | no fewer bytes once quality was matched |
| Search each image's quality | kept | 12% to 25% fewer bytes, within the time budget |
| Quantise everything to 256 colours | dropped | too slow: 158 ms at the 95th percentile (budget 120) |
| Keep the alpha as a separate mask | dropped | its own tests fail (it breaks on images without transparency) |

The transparency fix is the turning point: until it is kept, logos keep the quality goal out of
reach, the tuner sits at the top of its range, and everything costs the bytes of quality 95. Once
it is kept, the tuner turns the setting down by itself within a minute or two, and the bytes served
fall to a fraction. That is the quality loop doing its job, unlocked by the lab.

When the notebook runs out, the stand-in researcher has nothing more to propose and `ideas-ready`
stays off; with `FACTORY_AI=claude` the researcher reads the results and keeps going.

## The numbers

Each window of the last 48 images is a first-order smoothing of what the batch just served, written
as an equation: `(auxiliary.batch-quality - stock.quality) / window-time`. The window is 38.4 s
long (`world/customers.py`), and a moving average lags by half its length, so `window-time`, the
smoothing with the same lag, is 19.2 s (Sterman ch. 11.5); the images compared while a candidate
runs, `images-per-hour * MIN(stock.experiments, 1)`. Both are marked to estimate, since a percentile
is only nearly a mean: the Fit page shows how well the replay follows each window, and proposes what
the record supports.

## What to try

- `FACTORY_AI=claude ergostat run`: the researcher reads every result so far (`bin/py bin/lab.py
  history`) and the code, and proposes its own ideas; the developer implements them in a branch.
  Their prompts are in `prompts/`. The researcher runs on Sonnet and the developer on Haiku by
  default (`FACTORY_RESEARCHER_MODEL`, `FACTORY_DEVELOPER_MODEL`, or `FACTORY_MODEL` for both).
- Change the quality goal (`hold: "== 0.93"` in `service.yaml`; the tuner is told it on every
  run): lower is cheaper, and every experiment is judged there.
- Change the time budget (`candidate-fast` in `rollout.yaml`) and watch slow ideas pass.
- Add an idea to `bin/ideas.py` (a wrapper around `prepare` or `choose`, like the others).

## What is real and what stands in

The compression, the measurement, the builds (a git repository, a branch per hypothesis, its own
tests), the candidate running on the same images as production, and every decision are real. The
images are generated, so the example needs no downloads. The stand-in researcher and developer work
from a fixed notebook; with `FACTORY_AI=claude` both are Claude Code sessions that get only the
results, the code and the tools.
