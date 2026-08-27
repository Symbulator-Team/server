# tools

## `verify_lesson.py` — the examples, checked against the book

Runs every entry of one `.cir` file in `../examples/` through the real app
and prints what a reader would see beside what that lesson's chapter
prints. This is how the 322 worked examples were verified.

    py verify_lesson.py Lesson_03
    py verify_lesson.py Lesson_03 --only 13
    py verify_lesson.py Lesson_03 --quiet      # only entries that disagree

The expected answers live beside it as `Lesson_*.expected.json`, one file
per lesson, keyed by entry name. They were transcribed from the chapters;
where an answer changes, the chapter and the JSON have to move together.

**It reads `nodes`, `elements` and `extras`, never `values`.** An earlier
version read `values`, which is the exact substitution dictionary the
Evaluate card is fed — it ignores the Rounding and SI settings entirely, so
an entry with the wrong rounding looked identical to one with the right
rounding and every check passed. What a reader actually sees is the
formatted `plain` strings, and those are what this compares.

Two categories in the output are not the same thing:

* **"entr(ies) with a problem"** — a real disagreement, or an entry that
  does not solve. This should be 0, with one exception: Lesson 4's
  Bo2 Example 3.11 is *supposed* to fail, because the chapter teaches it
  as a failure and then shows the way round it.
* **"whose book names were not found among the answers"** — the expected
  text mentions a name the run did not produce. Usually the answer comes
  from a mini-tool an input file cannot invoke (the gain examples), so it
  is recorded in the entry's `note:` instead. Worth reading, not alarming.

A full sweep takes roughly half an hour. Run it after anything that touches
value parsing, formatting, or the solver.
