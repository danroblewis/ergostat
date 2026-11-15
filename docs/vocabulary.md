# Vocabulary: system dynamics and control engineering

The common terms of the two fields ergostat combines, listed separately, followed by the prior art
that already combines them. Use it to name things in ergostat the way practitioners would.

## System dynamics

The field founded by Jay Forrester (*Industrial Dynamics*, 1961) for the behaviour over time of
systems of accumulations and feedback. Tools: Stella/iThink, Vensim, AnyLogic, Insight Maker;
the interchange standard is XMILE.

**Building blocks (stock-and-flow diagrams)**

| Term | Meaning |
|---|---|
| Stock (level, accumulation, state variable) | What accumulates; integrates its flows over time |
| Flow (rate) | A rate of change of a stock: inflow, outflow; a biflow can run both ways |
| Valve (flow regulator) | The symbol on a flow's pipe where its rate equation lives; not a separate element |
| Source, sink (cloud) | The boundary: where flows come from or go to outside the model |
| Converter (auxiliary, variable) | A computed value: an equation of other quantities |
| Constant (parameter) | A fixed value |
| Connector (information link) | An arrow carrying information from one element to another's equation |
| Table function (graphical function, lookup) | A nonlinear relationship given as a curve or table |
| Delay | Material delay (things in transit) or information delay (perception lags); first-, third-order, pipeline |
| Conveyor, queue, oven | Stella's special stocks: transit with a fixed time, FIFO, batch processing |
| Smoothing (SMOOTH) | Exponential averaging; how perceptions and forecasts lag reality |
| Ghost (shadow, alias) | A second picture of the same element, to keep a diagram readable |
| Module (submodel, sector) | A part of a model, with inputs and outputs |
| Arrays (subscripts) | Many copies of a structure (per product, per region) |
| Co-flow, aging chain | Structures that track an attribute alongside a flow, or a stock through stages |

**Feedback and structure**

Causal loop diagram (CLD); link polarity (+/−, same or opposite direction); feedback loop;
reinforcing loop (R, positive); balancing loop (B, negative, goal-seeking); loop dominance and
shifting dominance; goal (desired state); discrepancy (gap); adjustment time (time constant);
perception delay; policy (decision rule): the equation that sets a flow from the information
available; bounded rationality; endogenous versus exogenous; model boundary (boundary chart);
mental models.

**Behaviour modes**

Exponential growth; goal seeking; S-shaped growth; oscillation; overshoot and collapse;
overshoot and oscillation; equilibrium (steady state); reference mode (the observed pattern a
model must reproduce); behaviour-over-time graph; bullwhip effect (order swings amplifying up a
supply chain).

**System archetypes** (Senge and others)

Limits to growth; shifting the burden; eroding goals; escalation; success to the successful;
tragedy of the commons; fixes that fail; growth and underinvestment; accidental adversaries.

**Practice**

Dynamic hypothesis; simulation; time step (DT); integration method (Euler, Runge-Kutta);
dimensional (unit) consistency; calibration; validation and confidence building; sensitivity
analysis; policy analysis; scenarios.

## Control engineering

The field of making a system behave as wanted using feedback: from servomechanisms and process
control to modern state-space and optimal control. Industrial practice adds instrumentation and
programmable controllers.

**Elements of a loop**

| Term | Meaning |
|---|---|
| Plant (process, system) | What is controlled |
| Controlled variable (process variable, PV, output y) | What is measured and held |
| Reference (setpoint, SP, command r) | What it should be |
| Error (e = r − y) | How far off |
| Controller (compensator) | The designed block: turns the error and other inputs into a command |
| Manipulated variable (MV, control input, control effort, u) | The command |
| Actuator (final control element) | What acts on the plant: valve, pump, motor, heater, drive |
| Sensor (transducer, transmitter) | What measures the controlled variable |
| Disturbance (load) | Inputs from outside that push the output |
| Measurement noise | Error added by the sensor |
| Feedback path | Measurement back to the comparator |
| Feedforward path | Measurement of a disturbance, used before it shows in the error |
| Summing junction (comparator) | Adds and subtracts signals |
| Takeoff (branch) point | One signal sent to several places |
| Block | A function from input signals to output signals |
| Signal | A value over time carried between blocks |

**Kinds of block** (as in Simulink and in IEC 61131 function blocks)

Gain; sum; product; integrator; differentiator; transfer function; filter (low-pass, high-pass);
lead, lag and lead-lag compensators; transport delay (dead time); saturation (limiter); rate
limiter; dead zone (deadband); backlash; hysteresis; relay (on-off); quantizer; lookup table
(function generator); switch; selector (min, max, high select, low select); comparator; logic
gates (AND, OR, NOT); latch (set-reset, flip-flop); timers (on-delay TON, off-delay TOF, pulse
TP); counters (up CTU, down CTD); sample and hold (zero-order hold); alarm (high, high-high,
low, low-low limits); subsystem (a block containing a diagram).

**Kinds of controller and control structure**

Open loop; closed loop (feedback); on-off (bang-bang, with hysteresis); proportional (P);
proportional-integral (PI); proportional-integral-derivative (PID); lead-lag compensation;
cascade (primary and secondary, master and slave loops); feedforward; ratio control; split-range
control; override (selector) control; gain scheduling; model predictive control (MPC); state
feedback; observer (estimator); Kalman filter; linear-quadratic regulator (LQR, LQG); adaptive
control; robust control (H-infinity); fuzzy control; sliding-mode control; supervisory control;
servomechanism (servo); regulator problem (hold a setpoint against disturbances) versus servo
problem (follow a changing setpoint).

**Analysis**

Transfer function; poles and zeros; characteristic equation; order (first, second); time constant;
gain (static gain); damping ratio; natural frequency; step response; impulse response; rise time;
settling time; overshoot; steady-state error (offset); stability; loop gain; root locus; Bode
plot; Nyquist plot; gain margin; phase margin; bandwidth; frequency response; sensitivity
function; robustness; disturbance rejection; setpoint tracking; linearisation about an operating
point; state space (A, B, C, D); SISO and MIMO; transfer-function matrix; controllability;
observability; discrete time; z-transform; sampling rate; aliasing; limit cycle; chattering.

**Practical issues**

Integral windup and anti-windup; bumpless transfer; tuning (Ziegler-Nichols, Cohen-Coon,
lambda tuning); derivative kick; actuator saturation; stiction; valve characteristic (linear,
equal percentage, quick opening); valve positioner; auto/manual mode; setpoint ramping; interlock.

**Industrial practice**

Piping and instrumentation diagram (P&ID); instrument tags (LIC: level indicating controller,
FIC: flow, TIC: temperature, PIC: pressure); distributed control system (DCS); programmable logic
controller (PLC); SCADA; HMI; alarm management (priorities, flooding, shelving); safety
instrumented system (SIS); IEC 61131-3 (PLC languages and function blocks); IEC 61499
(distributed function blocks).

## Comparison of terms

The same idea in each field, and what ergostat calls it. A dash means the field has no usual term
for it.

| Idea | System dynamics | Control engineering | ergostat |
|---|---|---|---|
| What accumulates | Stock (level) | State variable; the plant's integrator, whose output is the controlled variable (PV, y) | Stock |
| What changes it | Flow (rate): inflow, outflow | Plant input (and output) rate | Flow |
| A change nobody controls | Exogenous flow; an input from outside the boundary | Disturbance (load), d | Disturbance (a flow with no valve) |
| A change that can be commanded | Flow whose rate equation depends on a decision | Manipulated variable (MV, u) applied through the actuator | Flow with a valve |
| Where a rate is set | Valve symbol: where the flow's rate equation lives | Actuator (final control element) | Valve |
| The rule that decides a rate | Policy (decision rule) in the flow's equation | Controller (control law, compensator) | Controller |
| What we want | Goal (desired state) | Reference (setpoint, SP, r) | Goal |
| How far off | Discrepancy (gap) | Error, e = r − y | Error (and "off by") |
| How we know | Information link from the stock (measurement implied) | Sensor (transmitter), ym | Sensor |
| Information between elements | Connector (information link) | Signal | Signal (a reference to a port or stock) |
| A computed value | Converter (auxiliary) | Block (function) | Block |
| A fixed value | Constant (parameter) | Parameter (gain, setpoint value) | A value in the configuration |
| A curve or table | Table (graphical) function | Lookup table (function generator) | Lookup block |
| A lag in seeing | Information delay; perception delay; smoothing | Measurement lag; first-order lag; low-pass filter | Sensor period; stale readings |
| A lag in moving | Material delay; pipeline; conveyor | Transport delay (dead time) | Valve delay ("opens 42s after") |
| How fast it corrects | Adjustment time | Time constant (and gain) | Back in (recovery time) |
| Outside the model | Source and sink (clouds); model boundary | Outside the plant; exogenous inputs | Outside (`from`/`to` left out) |
| A goal-seeking loop | Balancing loop (B, negative) | Negative feedback loop (closed loop) | Loop (holding, off) |
| A self-amplifying loop | Reinforcing loop (R, positive) | Positive feedback (unstable) | — |
| No feedback | Open loop (no information link back) | Open loop | Open loop (`open_loop`) |
| Acting on the disturbance itself | — (a decision reading an input flow) | Feedforward | Feedforward |
| Loops inside loops | Nested structure; modules | Cascade control (primary, secondary) | Servo (an agent session), cascade |
| A part of the model with inputs and outputs | Module (submodel, sector) | Subsystem | System (a label), subsystem (planned) |
| The most a mechanism can do | — (a flow limited in its equation) | Saturation (limiter) | Valve `max`; saturated |
| Asking for more than can be done | — | Integral windup | Work piling up; "falling behind" |
| Stopping that | — | Anti-windup | Skipping a run while the last waits; clamping commands (planned) |
| Which loop governs now | Loop dominance (shifting dominance) | Dominant poles | — |
| Overshoot, oscillation | Overshoot and oscillation (behaviour modes) | Overshoot, underdamping, limit cycle | Crossings; time off |
| Resting state | Equilibrium (steady state) | Steady state; operating point | Holding |
| A measured pattern to explain | Reference mode | Data for system identification | The record |
| Inferring the model from data | Calibration | System identification | Discovery (planned) |
| What can be known | — | Observability | A stock with no sensor |
| What can be changed | — | Controllability | A goal no controller serves (missing feedback) |
| Amplification along a chain | Bullwhip effect | Noise or disturbance amplification | Loops in series; work piling up |
| Who does the work | — | — (machines are outside the theory) | Agent (person, ai, program, rule) |

## Prior art: the two combined

- **System dynamics came from control engineering.** Forrester worked in MIT's Servomechanisms
  Laboratory during and after the Second World War, building feedback controls for radar and gun
  mounts, and applied feedback control thinking to a General Electric production-and-inventory
  problem; the order swings he found are now called the bullwhip effect. *Industrial Dynamics*
  (1961) is the field's founding book.
  ([Wikipedia: Jay Wright Forrester](https://en.wikipedia.org/wiki/Jay_Wright_Forrester);
  [MIT Technology Review](https://www.technologyreview.com/2015/06/23/167538/the-many-careers-of-jay-forrester/))
- **Control theory applied to system dynamics models of production.** Towill's IOBPCS family
  (inventory and order based production control system, from the early 1980s; APIOBPCS adds
  work-in-progress control, 1994) draws production planning as block diagrams and analyses
  stability, bullwhip and inventory drift with control theory; Disney and Towill extended it.
  ([Disney and Towill, eliminating inventory drift](https://orca.cardiff.ac.uk/39539/1/Eliminating%20inventory%20drift%20in%20supply%20chains%20pre-print.pdf);
  [a 2022 System Dynamics Society paper on IOBPCS](https://proceedings.systemdynamics.org/2022/papers/P1298.pdf))
- **Control theory applied to computing systems.** Hellerstein, Diao, Parekh and Tilbury,
  *Feedback Control of Computing Systems* (Wiley-IEEE, 2004), from IBM Research: queueing and
  black-box models, PID and state-space control of web servers and databases. Philipp Janert,
  *Feedback Control for Computer Systems* (O'Reilly, 2013), is a practitioner's version.
  ([Wiley](https://www.wiley-vch.de/de/fachgebiete/ingenieurwesen/feedback-control-of-computing-systems-978-0-471-26637-2);
  [MIMO control of an Apache web server](https://cs.uwaterloo.ca/~brecht/servers/readings-new/acc02final2.pdf))
- **Autonomic computing.** IBM's MAPE-K loop (monitor, analyse, plan, execute, over shared
  knowledge) for self-managing systems, and a research literature reading it as a control loop.
  ([Rutten, Marchand, Simon: feedback control as MAPE-K loop](https://hal.archives-ouvertes.fr/hal-01285014))
- **Kubernetes controllers** are the most widespread everyday instance: a controller reads the
  desired state and the observed state and acts to reconcile them, in a loop.

What is new in ergostat is not the combination but its subject: a model of a software
organisation in which the machines are agents (AI agents, programs, people), judged by measured
stocks; and finding the feedback that is missing, or that exists unnamed, in production systems,
so the critical loops can be maintained.
