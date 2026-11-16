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
```

Then the page `ergostat run` prints, or:

```bash
ergostat loop                     # the goals: holding or off
ergostat item --kind case         # the benchmark: which of the thirty cases squeeze meets, and how well
ergostat item --kind hypothesis   # every experiment, its state, and (ergostat item hypothesis/3) what it measured
ergostat explain small-images     # the whole chain, from the researcher to the bytes served
ergostat run --stop
```

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
- the `rollout` reads `bytes-saved` (a 90% confidence interval over the images both builds saw),
  the candidate's failures and time, and a guardrail on every kind of image. While the candidate
  is better, it gets more of the traffic (5%, 25%, 50%, 100%: `rollout-share`, and what is served
  moves with it); then it is kept, merged, and production runs at its matched quality. If it fails
  on any image, is slow (over 120 ms at the 95th percentile), is much worse for some kind of image,
  or shows no difference, it is rolled back.

This is what makes an AI developer's mistakes safe: a broken change shows up as measured failures
on a small share of traffic, and the loop pulls it back. Nobody has to notice.

**3. The research loop (hours, here minutes): the experiments.** Hypotheses are items
(`hypothesis/3`: proposed → building → testing → kept or dropped). The `researcher` proposes while
fewer than two wait (`ideas-ready`); the `developer` builds the oldest whenever the candidate slot
is empty (`one-running`). `small-images` (bytes per megapixel served ≤ 20) is the target the whole
lab chases: `ergostat explain small-images` traces it from the researcher, through the ideas and the
experiment, to the rollout and the bytes served.

## The benchmark: what squeeze can do

Bytes served depend on what customers happen to send. How good squeeze *is* does not: thirty fixed
images (five of each kind) are the benchmark (`world/benchmark.py`), each a **case** with a target,
the kilobytes per megapixel it should need while still looking good enough (SSIM 0.93; the quality
setting is searched, so it measures the code, not the setting). Like recorded signals a radio must
decode, they are not tests that pass or fail but a count of what the product can do:

- each case is an item (`case/logo-3`: met or unmet, its size now and its best so far): the Items
  tab's `case` table is squeeze's scoreboard;
- **`capabilities`** is the stock of cases met, filled by `gained` and drained by `lost`, both driven
  by releases; the goal `every-case` is all thirty (the noisiest photos may stay out of reach);
- **`benchmark-score`** is the kilobytes per megapixel all thirty need (lower is better): one number
  for how good squeeze is now;
- the `benchmark` block measures each release once; every candidate is measured when it is
  submitted, and rolled back if it loses a case production meets (a regression no amount of live
  traffic in one hour might show).

squeeze as handed over meets 2 of the 30; the transparency fix and the encoder's optimisation take
it to about 9; screenshots, line art and logos need a flat-image policy that does not break
grayscale photos; the noisy photos need something better than any idea in the stand-in's notebook.

## Variables, not stocks

Quality, bytes per megapixel, the quality setting, the rollout share: none of these accumulate, and
nothing flows into them. They are **variables** (`variables:` in the YAML): measured ones are what
the goals hold (process variables), set ones are the knobs the controllers turn (manipulated
variables). The diagram draws them as ovals; `driven-by` says what each follows. The lab's own work
is stocks and flows: ideas waiting, the experiment running, improvements kept.

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

## What to try

- `FACTORY_AI=claude ergostat run`: the researcher reads every result so far (`bin/py bin/lab.py
  history`) and the code, and proposes its own ideas; the developer implements them in a branch.
  Their prompts are in `prompts/`. The researcher runs on Sonnet and the developer on Haiku by
  default (`FACTORY_RESEARCHER_MODEL`, `FACTORY_DEVELOPER_MODEL`, or `FACTORY_MODEL` for both).
- Change the quality goal (`hold: "== 0.93"` in `service.yaml`; the tuner is told it on every
  run): lower is cheaper, and every experiment is judged there.
- Change the time budget (`TIME_BUDGET` in `bin/lab.py`) and watch slow ideas pass.
- Add an idea to `bin/ideas.py` (a wrapper around `prepare` or `choose`, like the others).

## What is real and what stands in

The compression, the measurement, the builds (a git repository, a branch per hypothesis, its own
tests), the candidate running on the same images as production, and every decision are real. The
images are generated, so the example needs no downloads. The stand-in researcher and developer work
from a fixed notebook; with `FACTORY_AI=claude` both are Claude Code sessions that get only the
results, the code and the tools.
