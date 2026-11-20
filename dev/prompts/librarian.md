You classify a review's blocking findings against the factory's review lessons. Answer with one fenced JSON block and
nothing else.

# The lessons (each with the shapes it was already seen as)

{lessons}

# The findings ({review})

{findings}

# Answer

For each finding, by its number:

```json
[{"finding": 1, "class": "lesson-3 | new", "name": "for new: the class of mistake in a few words",
  "shape": "the shape it takes here, in the lessons' style (a short clause)",
  "new_shape": true}]
```

`new_shape` is true only when the lesson's "Seen as" does not already cover this shape. A finding that is no class of
mistake (a missing doc line, a typo) is `"class": "none"`.
