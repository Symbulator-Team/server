# schematic_lab — measuring the drawer

Research tools for `repos/solver/symbulator/schematic.py`. Nothing here
runs in a build; `review_schematics.py` one directory up is the guard
that does. These are for **answering questions about the drawings** —
how big they are, what collides, which ones a change moves, and whether
an objective agrees with the judgements Roberto has already made.

They live in the repository rather than in a session scratchpad
deliberately. The 10 Sep 2026 handover opens by listing four tools the
retiring session had built and lost, and the hour the next one spent
walking back into the same two traps.

Run them from this directory: `py survey.py`, `py band.py`, and so on.
They add `repos/solver` and `repos/server` to `sys.path` themselves, so
they measure the **working tree**, not whatever `pip` has installed.

## The tools

| file | what it answers |
|---|---|
| `common.py` | every built-in entry and the description the app would actually draw. Import this, do not re-enumerate |
| `quality.py` | Roberto's seven values over one drawing, with the evidence beside each number |
| `survey.py` | all 356 measured into `survey.json`, worst first per value |
| `probe.py` | every line, dot and label of one drawing. Reach for this the moment a number looks wrong |
| `whichgap.py` | which two boxes make a drawing's tightest gap |
| `snapshot.py` | render all 356 into a directory, as UTF-8 bytes |
| `at_rev.py` | the same, as some past revision drew it, by swapping `schematic.py` in place and putting it back in a `finally` |
| `diffsnap.py` | which drawings differ between two snapshots |
| `energy.py` | scores candidate objective orderings against drawings he has ruled on |
| `validate.py` | the same pairs, term by term, so you can see what a ruling actually cost |
| `band.py` | how much of the node-row-to-rail band is air |
| `gaps.py` | the vertical gaps that already exist in the band |
| `hslack.py` | how much of each column gap is air † |
| `leadmin.py` | the clearance the book already stands at † |
| `labelsep.py` | how close two labels come, parsed from snapshot SVGs so it works on any revision |
| `gallery.py` | the before/after page. **This is the deliverable** — he reviews by eye |
| `variations.py` | one circuit at several settings, for a taste decision |

† needs the solver's **`sch-relax`** branch, which is where #373 lives.
They call `_render_once(..., out=)` and `_band_content`, neither of
which exists on `main`, and they fail loudly rather than measuring
something else. Everything else in the table runs against `main`.

A typical round:

    py at_rev.py <rev-before-your-change> before snapshot.py
    py snapshot.py after
    py diffsnap.py before after            # the blast radius
    py at_rev.py <rev> survey_before.json survey.py
    py survey.py survey_after.json
    py energy.py survey_before.json survey_after.json
    py gallery.py before after survey_before.json survey_after.json out.html

## The traps these exist to avoid

**Fetch an old file as bytes.** `subprocess.run(..., text=True)` decodes
git's UTF-8 through the console code page and turns every `Ω` into two
characters. That reported 284 changed drawings when the real number was
seven. `at_rev.py` uses `capture_output=True` and writes `p.stdout`.

**Swap the file in place.** Rendering an old revision into a *copied*
package makes the copy the variable. `at_rev.py` writes into the real
tree and restores in a `finally`, then reads the file back and asserts.

**Strip `<g transform=…>` before measuring wires — or don't measure the
SVG at all.** A symbol draws its leads in its own frame. `quality.py`
reads the canvas instead, where every line is in one frame: merged wire
runs plus each element's own axis segment.

**Count crossings as the drawer's own hop arcs** (`A5 5 0 0`), never by
intersecting the wire list — that misses every crossing over a lead.

**A body reports itself twice.** An op-amp draws its wedge as
`OP_INK_BANDS` = 24 ink strips *and* registers an obstacle over the
same rectangle. An unguarded pair test returns 2.4px as the tightest gap
in the drawing, on every op-amp drawing in the book. `gaps.py` and
`schematic.py`'s own `_band_content` both collapse them.

**A near-miss is not a near-corner join.** Two line ends near each other
*diagonally* are two corners. The defect is two ends that share an axis
and miss — every one #371 measured is two ends on one `x`. And the
op-amp's own pin spacing (`h/2` = 29px) is the symbol, not the layout;
#371 counted it.

**Before believing a green check, break the thing it checks.** Every
number in the write-ups here was produced by a tool that was first made
to go red on purpose: `diffsnap.py` against a one-pixel `ROW_H` change
(356 moved), and the relaxation's own acceptance test against
`LEAD_MIN = 2` (26 harness findings).

**Two budgets, not one.** A relaxation that compares a single collision
total will spend a near-miss it started with on a real overlap. That is
exactly what happened: `iCO` sat 17.5px from `8∠-40°` in AS7's Example
10.13 — one near-miss — and the narrowed drawing had them overlapping —
one overlap — so the totals matched and the fault shipped past a green
check. `_collisions` returns `(hard, soft)`.
