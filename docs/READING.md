# Reading list: the canon behind ergostat

The books and papers the two disciplines are judged by, chosen for this project: modelling running software and
the work of AI agents as stocks, flows and feedback loops. ★ marks where to start.

## System Dynamics

- ★ **John Sterman, *Business Dynamics: Systems Thinking and Modeling for a Complex World*** (2000). The reference.
  Ch. 3 (the modelling process), 5–6 (causal loops, stocks and flows), 8–9 (structure and behaviour), 11 (delays),
  13 (modelling decisions), 21 (tests for building confidence in models). Most of what ergostat calls modelling is in it.
- ★ **Donella Meadows, *Thinking in Systems: A Primer*** (2008). Short, plain, the best first read; ends with
  leverage points.
- **Jay Forrester, *Industrial Dynamics*** (1961). The founding text: information feedback in firms, and why delays
  and policies, not people, make the behaviour.
- **John Morecroft, *Strategic Modelling and Business Dynamics*** (2nd ed., 2015). A gentler modeller's handbook,
  good on bounded rationality and decision functions.
- **George Richardson, *Feedback Thought in Social Science and Systems Theory*** (1991). Where the feedback idea came
  from, and how SD and control engineering diverged.
- **Rahmandad, Oliva and Osgood (eds.), *Analytical Methods for Dynamic Modelers*** (2015). Calibration,
  loop dominance, sensitivity: the numbers side.
- Papers on the dynamics of project work, close to agents doing software work:
  - ★ Ford and Sterman, "Dynamic modeling of product development processes", *System Dynamics Review* 14(1), 1998.
    The rework cycle.
  - Lyneis and Ford, "System dynamics applied to project management: a survey", *System Dynamics Review* 23, 2007.
  - Repenning and Sterman, "Nobody ever gets credit for fixing problems that never happened", *California
    Management Review* 43(4), 2001. Firefighting and the capability trap.

## Control engineering

- ★ **Karl Åström and Richard Murray, *Feedback Systems: An Introduction for Scientists and Engineers*** (2nd ed.,
  2021; free online). The modern introduction, written for people outside control.
- **Franklin, Powell and Emami-Naeini, *Feedback Control of Dynamic Systems***. The standard undergraduate text: block
  diagrams, root locus, frequency response, state space.
- **Katsuhiko Ogata, *Modern Control Engineering***. The other standard text; the block-diagram conventions ergostat
  draws come from books like these two.
- ★ **Hellerstein, Diao, Parekh and Tilbury, *Feedback Control of Computing Systems*** (2004). Control theory applied
  to software systems: admission control, queues, servers. The closest book to what ergostat does.
- **Philipp Janert, *Feedback Control for Computer Systems*** (2013). A practical, programmer's version of the same.
- **Åström and Hägglund, *Advanced PID Control*** (2006). How real loops are tuned, with anti-windup, feedforward and
  gain scheduling.
- **Åström and Wittenmark, *Computer-Controlled Systems*** (sampling and holds) and ***Adaptive Control***
  (controllers that tune themselves).
- **Lennart Ljung, *System Identification: Theory for the User*** (2nd ed., 1999). Learning a process's model from
  its record.
- **Seborg, Edgar, Mellichamp and Doyle, *Process Dynamics and Control***. Process control as plants are run:
  cascade, ratio, feedforward, the control hierarchy.
- **Cassandras and Lafortune, *Introduction to Discrete Event Systems***. Supervisory control of event-driven
  systems (Ramadge–Wonham): the theory for states, events and what a supervisor may block.
- **Skogestad and Postlethwaite, *Multivariable Feedback Control***. For when loops interact; ch. 10 on control
  structure design (which loops, at which level, at which time scale) is worth reading on its own.

## Supervision, safety and the operator

- ★ **Nancy Leveson, *Engineering a Safer World*** (2011; free online). Safety as a control problem (STAMP):
  accidents as inadequate control, hazards as constraints. The most direct bridge to supervising AI work.
- **Thomas Sheridan, *Telerobotics, Automation, and Human Supervisory Control*** (1992). The human as the outer loop.
- **Bill Hollifield and Eddie Habibi, *Alarm Management: A Comprehensive Guide*** and **Hollifield et al., *The
  High Performance HMI Handbook***. The practice behind ISA-18.2 and ISA-101: what an operator should see, and when
  to interrupt them.
- Standards, read through the two books above rather than whole: ISA-88 (batch control: modes and states), ISA-18.2
  (alarm management), ISA-101 (operator interfaces), IEC 61511 (safety instrumented systems, layers of protection).

## Cybernetics

- **W. Ross Ashby, *An Introduction to Cybernetics*** (1956; free online). Requisite variety: a regulator must
  have as many responses as the disturbances it faces, which is why an agent handles more kinds than a fixed loop.
- **Stafford Beer, *Brain of the Firm*** (2nd ed., 1981). The Viable System Model: operations, coordination,
  control, intelligence and policy as recursive subsystems. A cybernetic template for a Coordinator.

## Flow and queues

- **Donald Reinertsen, *The Principles of Product Development Flow*** (2009). Cost of delay, WSJF, queues and WIP
  in knowledge work.
- **Hopp and Spearman, *Factory Physics***. Little's law and variability in production lines.
- **Mor Harchol-Balter, *Performance Modeling and Design of Computer Systems*** (2013). Queueing theory for
  scheduling and priority.

## A reading order

1. Meadows, then Sterman ch. 1–6.
2. Åström and Murray ch. 1–3, then Hellerstein et al.
3. Ford and Sterman's rework paper, and Leveson.
4. Then whatever the work at hand needs: Sterman ch. 21 for tests, Ljung for identification, Cassandras and
   Lafortune for supervisors, Hollifield for the operator.
