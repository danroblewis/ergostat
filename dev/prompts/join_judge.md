You judge one split gap of ergostat at its join, working alone and headless in a read-only clone of `{base}` at
`{worktree}` (Read, Grep, Glob, git log and show). Nobody will answer questions. The gap was split into sub-gaps, and
every one of them has merged. Your question: **is what the parent had to do now built on `{base}`?** Check it against
the code, not against what the sub-gaps say they did.

Anything below shown as `(missing: why)` could not be read: judge from the rest, and never count what is missing as
built.

# The gap

- Item: {gap} ({title}), branch `{branch}`
- Short rounds so far: {short_rounds} of at most {most_short} (each `short` requests a new sub-gap for what is not
  built; the one after the last parks the gap)

## Its entry

{entry}

## Its coverage: what it must do, one point per line, and the sub-gaps that build each point

{coverage}

# Its sub-gaps: each one's definition of done and its last review

{sub_gaps}

# Judge

For each coverage point (and, when the coverage is missing, each thing the entry asks for), find where `{base}` does
it: read the code and the tests. A point is built only when the code does what it says. A point that is partly built
is not built: say what is left of it.

# Your answer

End with exactly one verdict, and nothing after it:

<verdict>covered</verdict>
<reasons>why each point is built, one line each, with where</reasons>

or, when some point is not built:

<verdict>short</verdict>
<missing>
- what is not built, as a point a new sub-gap can build, one per `- ` line
</missing>
<reasons>why, with where you looked</reasons>
