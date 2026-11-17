"""The intent judge (SPEC §12i; harness parity §2.2): finished work held to what the owner meant before it counts as
done. A piece of work that says it is done (it entered its judged state; its tests passed) is judged against its
done-when, the confirmed decisions and corrections in its scope, and the owner's messages about it; the verdict, with
its evidence, is an ``ergostat.verdict`` item and the work's field ``intent``.

- ``brief``: what the work is, and what it is held to;
- ``standin``: the free judge (rules on words: what the owner ruled out, brought in by the work);
- ``ai``: the judge on a model, its evidence checked against the work;
- ``judge``: the pass, on the judge block's clock; the policy for work held back;
- ``record``: the verdict's events, and the owner's acts (overrule a verdict, reopen work);
- ``outcomes`` and ``measures``: what became of work after it was accepted, and the rates goals read."""
