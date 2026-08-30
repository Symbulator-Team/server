# tools

## `review_schematics.py` — every example, drawn and checked

Renders every entry of every `.cir` book in `../examples/` with
`symbulator.schematic.to_svg` into a browsable HTML gallery, and checks
each drawing: exceptions, overlapping labels, wires through element
bodies or op-amp triangles (measured by instrumenting the canvas, not
by squinting), unusual hop counts, extreme sizes. `report.txt` in the
output folder lists findings worst-first.

    py review_schematics.py                # gallery into the temp folder
    py review_schematics.py C:\some\dir    # or a folder of your choosing

A clean run ends `failed=0 with_issues=0` — the state the Aug 2026
schematic rework left all 322 tutorial circuits in, and the bar any
schematic change should keep. It prefers a sibling `repos/solver`
checkout over the installed package, so it reviews the working tree.
Run it after anything that touches `schematic.py`.

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

## `i18n.py` — the nine languages (#197)

The app speaks nine languages by way of a **client-side dictionary applied
in the page**, and it has to: two of the three builds are static files with
Pyodide in the tab, so anything server-rendered would translate the hosted
app and leave the downloaded one in English. This script is the machinery
around that dictionary.

    py tools/i18n.py scan     # how many units, and where
    py tools/i18n.py tag      # give every unit its data-i18n key,
                              # and regenerate i18n/en.json
    py tools/i18n.py pack     # write the dictionaries into the templates
    py tools/i18n.py check    # is everything in step?

**`en.json` is generated, not written.** The English lives in the template
markup and in the fallback argument of every `t()` / `tv()` call; a second
hand-kept copy of it would only drift. The other eight are hand-written and
are the only files a translator edits — then `pack`, and the block between
the `BEGIN/END i18n dictionaries` markers in each template is rewritten.
Each page carries only the keys it asks for.

A **translation unit** is the outermost element containing text whose
descendants are all inline, so a whole paragraph is one entry and a
translation may move the `<code>` or the `<a>` where its own word order
wants them. Three things are never units: anything inside
`class="notranslate"` (the wordmark, the build stamp, the syntax columns of
the reference tables), anything spanning a `server-only` marker (the
offline build deletes those blocks, and a dictionary copy would paint them
back), and the regions the page's own JavaScript writes into.

The **key** is a readable slug plus four hex of the English's SHA-1, so
editing the English mints a new key and the stale translation shows up as
an orphan in `check` instead of quietly staying on screen.

What `check` catches, all of it learned the hard way:

* a unit that is not tagged, or tagged with a key its English no longer
  hashes to;
* `en.json` disagreeing with the page, and orphans in any language;
* a translation that drops an `id`, a `href` or a `%{slot}` the English
  had — each of those fails silently at runtime, because dictionary values
  are written into the page as innerHTML;
* a translation that introduces a `<script>` or `<style>`;
* `t(key, ...)` with a **variable** key, which `en.json` can never see, so
  the string would fall back to English in all eight languages with
  nothing to say so;
* a new element kind or two-port description in `symbulator_ui.py` that no
  language has a word for yet.

`pack` escapes `<`, `>`, `&` and `{` inside every string, so no translation
can close the script element or grow a Jinja construct — `{#` in a template
took every server page down on 30 Aug 2026, and eight languages of new text
is a lot of new opportunity.
