# Why controllers and valves are separate

Control engineering draws the controller and the valve (the actuator) as separate blocks. The
easy answer, that controllers are low-power devices and valves need power and handle hazards, is
true but shallow. The real reasons are about analysis, nonlinearity, state and timescale. They
are collected here (the owner's notes, 2026-11-14), followed by what they mean for ergostat,
where the valves are often agents: machines, programs, AI agents and people that let a flow of
work happen.

## The distinction, in one place

Mathematically there is no difference. Every block in a block diagram is a function from input
signals to output signals; "controller", "actuator" (valve) and "sensor" are names for roles,
not kinds of mathematics. And the sensor-controller-valve arrangement is a pattern, not a law.

The role names still mean something:

- **The controller is the block you design.** It is the free choice, where intent goes: goals,
  priorities, limits, what to do when off. Everything else (the actuator, the plant, the sensor)
  is given: something to accept and model, not choose. Control engineering is the study of
  choosing that one block well, given the others.
- **The controller is not "the simple part".** Model predictive control solves an optimisation
  against a model of the whole plant at every step; actuators can be as simple as a solenoid.
  The "light controller, heavy valve" picture comes from the economics of process plants, not
  from the theory.
- **The controller is not required to be linear.** On/off (thermostats), constrained MPC,
  gain-scheduled, fuzzy and rule-based controllers are all nonlinear. Linearity is what the
  analysis tools want (Bode, Nyquist, root locus, stability proofs), because linear blocks
  compose predictably: superposition holds, small errors stay small, a few tests tell you how it
  behaves everywhere. Where analysis matters, engineers keep known nonlinearities outside the
  core block (gain scheduling, feedforward), not inside it.
- **Sensors and actuators decide what can be known and what can be changed.** Control theory
  makes this formal (observability and controllability): a state no sensor reads cannot be
  known, and a state no actuator moves cannot be controlled. Missing feedback is one of these.

The reasons below are why, in practice, the designed block is kept apart from the mechanisms it
commands.

## The reasons

### 1. Loop shaping needs the control law apart from the mechanics

The controller, G_c(s), is a linear or discrete compensator designed to shape the loop's
open-loop frequency response. Its job is pole-zero cancellation, phase margin enhancement and
error minimisation (for example, adding zeros to cancel sluggish process poles).

The valve or actuator, G_a(s), is typically modelled as a first- or second-order lag combined
with a pure integrator (representing stem travel speed), plus physical inertia and mass.

Conflating them into one block would bake the valve's mechanical dynamics into the control law.
That makes analytical loop shaping, root-locus analysis and stability proofs (Nyquist, Bode)
unnecessarily intractable, because the abstract control algorithm would be coupled to the
mechanical time constants of one particular valve body.

### 2. The valve's hard nonlinearities are kept in one place

Control theory loves linearity, and valves are notoriously nonlinear. A real control valve
introduces:

- **Backlash and stiction.** Static friction causes dead zones, where small changes in the
  controller's output produce no movement until breakaway force is reached.
- **Rate limits (slew rates).** A valve cannot move from 0% to 100% instantly; it is bounded by
  piston speed or motor torque.
- **Asymmetric flow characteristics.** Equal-percentage, linear and quick-opening trim profiles.

If these were part of the controller's state equations, standard linear design (and even model
predictive control) would break down, or need complex nonlinear compensation inside the
calculation engine. Kept separate, the controller can assume an idealised output, while a local
valve positioner handles the messy part with its own inner feedback loop, linearising the
valve's actual response.

### 3. Each keeps its own state, and the boundary is where saturation is handled

In a state-space representation (ẋ = Ax + Bu), controllers and valves have independent state:

- A PID controller's state includes the integral of the error (x_i = ∫ e dt) and its
  derivative filter.
- A valve's state includes its position, velocity, and internal chamber or pneumatic pressure.

Mixing them into one state matrix gives up modularity. When the integral winds up because the
valve is already 100% open and the error persists, the architecture handles it with explicit
anti-windup logic at the boundary between the controller's output and the actuator's input.
Separate blocks give a clean point at which to intercept saturation, apply constraints and
manage diverging state.

### 4. They run on different timescales

- A digital controller can run its loop every few milliseconds.
- A heavy valve has mechanical time constants of seconds or tens of seconds: fluid momentum,
  mass, the time to fill the actuator's volume.

Drawing them apart reflects that hierarchy: the controller is a fast, sampled decision engine;
the valve is a slower, continuous part of the plant that the engine drives. Separate blocks let
engineers use quasi-steady-state assumptions or reduced-order models when analysing stability
(singular perturbation).

## What this means for ergostat

**An AI agent can fill either role; its function decides which, not its complexity.**

- **As a valve**, it is coupled to the real system: it changes the repository, the docs, the
  tickets. It is judged by what it did to the stocks, not by its report. An AI agent session is
  more than a plain valve: it is a servo, given a target and looping inside until it gets there.
- **As a controller**, its output is only a decision or a command, never a change to the world.
  It is the policy written down at its level. What we want from it is not linearity but good
  behaviour at the level of the loop: monotone (more error never brings less action), bounded
  (no wild commands), consistent (the same situation gets much the same decision), and fast
  enough. ergostat can measure each of these.

Triage is an example: an AI agent sorting incoming items into buckets is a controller of the
routing kind (it decides where work goes; other machines do the work). Item by item it is a
discrete, nonlinear function; what the loop needs is a low, steady misroute rate and enough
throughput, both measurable. A known nonlinearity, such as different sorting by time of day, is
kept outside it, the way engineers would: switched or fed forward, not buried in the prompt. An AI
controller whose decisions are very consistent is a candidate to become a rule (the ladder).

Layered systems are the same picture repeated: at each level there is one designed block (the
policy) and the levels below, seen from outside, are its valves. A Fable supervisor commanding
Sonnet workers is supervisory control: an expensive policy over cheaper mechanisms. There is a
controller at every level; that is where each level's decisions are explicit, measured at the
boundary (command in, achievement out), and changeable.


In ergostat the valve is usually an agent, and every one of the four reasons carries over.

**1. The decision is a law; the agent is a mechanism.** A controller's law ("over 500 MB, rotate
until under 300") should not depend on which machine carries it out. Kept apart, the agent behind
a valve can move down the ladder (an AI agent, then a script, then a rule) without the control
law changing, and the law can be judged (does it hold its goal? does it oscillate?) on its own.
This is why roles name their machine (`by:`) and machines never name their roles.

**2. Agents are badly nonlinear actuators, and their nonlinearities belong to the valve.**

| In a valve | In an agent |
|---|---|
| Dead zone (stiction) | A job that only acts above a batch size; a person who won't bother for one item |
| Rate limit | `max` per run; how many jobs a machine runs at once |
| Backlash, breakaway | Cold starts; an AI session's setup; a valve in `advise` or `manual` mode, which waits for a human |
| Asymmetric characteristic | Deleting is fast, rebuilding is slow; scaling up takes minutes, scaling down seconds |
| Positioner (inner loop) | An agent that retries until the work is done and reports what it actually moved |

These belong in the valve's description (limits, minimums, concurrency, typical duration), so a
controller can be written as if its valve were ideal, and ergostat measures how far each valve is
from ideal (how long it takes to answer, how often it saturates).

**3. The command is the interface, and the boundary is where windup is caught.** A controller
should output a command ("move 50"), and the valve should report what it actually moved. The
difference between commanded and moved is the direct evidence of saturation, far better than
inferring it afterwards. Windup is common with agents: a controller keeps asking while the valve
is busy or at its limit, and requests pile up (a queue of jobs, repeated triggers, pull requests
nobody reviews, as in the deps example). Anti-windup lives at the boundary: clamp commands to the
valve's limits, don't queue a new command while the last one is still running (ergostat already
skips a run whose previous one is waiting), and record each refused or clamped command. Today
ergostat records only what was moved; it should record what was commanded as well.

**4. Controller cadence must respect the valve's time constant.** A controller deciding every
minute, driving an AI agent that takes ten minutes or a person who takes a day, will see the
error persist and keep pushing: overshoot, windup, oscillation. The rule from singular
perturbation applies directly: the controller should run fast relative to the stock it
watches, but not faster than its valve can respond, or it must account for the lag. ergostat
already measures the valve's lag (how long after a loop goes off its valve opens, and how long
until it holds again); it can compare that with the controller's cadence and say so.

**For the format,** this confirms the split: controllers carry a law and a cadence and output
commands; valves carry what to run, on which machine, and their limits (`max`, a minimum,
concurrency, an expected duration); the boundary between them, command in and amount out, is
recorded, and is where ergostat clamps, refuses and reports saturation.
