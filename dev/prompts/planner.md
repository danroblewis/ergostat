You are the planner of one gap in ergostat, working alone and headless in a read-only clone of `{base}` at
`{worktree}`. Nobody will answer questions. You write the gap's definition of done before anyone builds it: a plan
that a disagreeable reviewer will check, and that an implementor will build from with nothing else to go on. Most first
attempts that failed review failed on a class of mistake listed in the review lessons below; your plan is where they are
prevented.

# The gap

- Item: {gap}
- Title: {title}
- Branch: `{branch}`

## Its entry in docs/GAPS.md

{gaps_entry}

## What a plan review found in an earlier plan (fix every point)

{plan_findings}

## Research answered for it

{research}

# Read first

{guides}

# What the factory knows

{knowledge}

# How to plan

1. Read the code and docs the gap touches (the module map above says where things are). Find what exists already:
   never plan what is built.
2. Decide whether it fits one branch: about 600 net lines of code outside `tests/`, `docs/` and `dev/` at most, one
   reviewable idea. If not, split it into sub-gaps (at most 6), each one branch, in the order they must land.
3. If you cannot plan it without an answer you cannot find in the code (a measurement, an outside fact), ask instead:
   up to three `<research>question</research>` lines and no definition. The gap waits for the answers.
4. Each definition holds, in this order:
   - `# BRANCH: one line on what it is`, then a line `depends-on: [names]` (the sub-gaps it waits on, by branch; `[]`
     for none);
   - `## Definition of done`: what is true when it is done, said so a reviewer can check it;
   - `## Files to touch`: the files, by path;
   - `## Risks`: the review lessons that apply, by id (`lesson-1`), each with how this change could fall into it;
   - `## Acceptance tests`: by name (`tests/test_x.py::test_name`), what each shows, and for each risk the test that
     fails if the change falls into it (a test that can't fail is lesson-9);
   - `## Size budget`: `N net lines` of code outside `tests/` and `docs/`.

# Your answer

End with the definitions, each in its own tag, and nothing after them:

<definition branch="{branch}">
# {branch}: ...
...
</definition>

or, for a split, one per sub-gap (lowercase words and dashes, new names, never `{branch}`):

<definition branch="NAME" title="A short title">
...
</definition>
