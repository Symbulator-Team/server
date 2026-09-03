# -*- coding: utf-8 -*-
"""Run every built-in example's plot, the way the Plot card would.

#251 (3 Sep 2026). Since the plot keys became part of an entry, 67 of the
330 built-in entries carry a plot: a time plot, a Bode plot, a Bode plot
of a typed H(s), or a DC sweep. Each was sized from the entry's own
answer when it was written, but a plot is only proved by running it, and
nothing else in the project does -- `verify_lesson.py` posts the solve,
not the plot, and the schematic harnesses draw the circuit.

This script reads every book in `examples/`, and for every entry with a
`plottool:` calls the same ui function the app's endpoint calls
(`plot_time_ui`, `bode_ui`, `bode_tf_ui`, `sweep_ui`) with the entry's own
key, range and point count, plus its Expert Mode extras and its Define
lines expanded first. It fails on:

* a `plottool` the menu does not offer (`time` was shipped in two entries
  for a day; the menu's value is `plot_time`);
* a plot the engine refuses, quoting the engine's reason;
* a plot whose samples are not finite, or whose trace is flat -- a plot
  that draws a horizontal line is a wrong key or a wrong range;
* a range that does not run low to high.

    python tools/check_example_plots.py            # every book
    python tools/check_example_plots.py Lesson_11  # one book

Exit status 1 with every failure listed, so a book can be fixed in one
pass. Not wired into the build: it solves 67 circuits and takes a while.
Run it after touching a book, the plot tools or `symbulator_ui.py`.
"""
import glob
import io
import math
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SERVER = HERE.parent
sys.path.insert(0, str(SERVER))
os.chdir(SERVER)

from circuitbook import parse_book  # noqa: E402
import symbulator_ui as ui  # noqa: E402

MENU = {"plot_time", "bode", "bode_tf", "sweep"}


def extras(c):
    unks = [u.strip() for u in re.split(r"[,\s]+", c.get("unknowns", "") or "") if u.strip()]
    return c.get("equations", []) or [], unks, c.get("conditions", []) or []


def prepared_desc(c):
    desc = c["desc"].replace("\n", ":")
    defs = c.get("defines", []) or []
    if defs:
        d, err = ui.parse_defines(defs)
        if err:
            raise ValueError(err)
        desc = ui.expand_defines_in_desc(desc, d)
    return desc


def finite(xs):
    return [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]


def run_one(c):
    """Return "" when the entry's plot runs and draws something, else why not."""
    tool = (c.get("plottool") or "").strip()
    if tool not in MENU:
        return f"plottool '{tool}' is not a menu value ({', '.join(sorted(MENU))})"
    key = (c.get("plotkey") or "").strip()
    if not key:
        return "no plotkey"
    try:
        lo, hi = float(c.get("plotmin") or 0), float(c.get("plotmax") or 0)
        n = int(c.get("plotpoints") or 300)
    except ValueError as e:
        return f"range/points not numeric: {e}"
    if not lo < hi:
        return f"range {lo} .. {hi} does not run low to high"
    eqs, unks, conds = extras(c)
    if tool == "bode_tf":
        r = ui.bode_tf_ui(key, lo, hi, n)
        series = r.get("mag_db", []) if r.get("ok") else []
    else:
        desc = prepared_desc(c)
        if tool == "plot_time":
            r = ui.plot_time_ui(desc, key, lo, hi, n, eqs, unks, conds)
            series = r.get("y", []) if r.get("ok") else []
        elif tool == "bode":
            r = ui.bode_ui(desc, key, lo, hi, n, eqs, unks, conds)
            series = r.get("mag_db", []) if r.get("ok") else []
        else:
            x = (c.get("plotx") or "").strip()
            if not x:
                return "sweep with no plotx"
            r = ui.sweep_ui(desc, key, x, lo, hi, n, eqs, unks, conds)
            series = r.get("y", []) if r.get("ok") else []
    if not r.get("ok"):
        return "engine: " + str(r.get("error"))
    ys = finite(series)
    if len(ys) < 3:
        return "no finite samples"
    if max(ys) - min(ys) < 1e-9:
        return f"{key} is flat over the range"
    return ""


def main(argv):
    books = sorted(glob.glob("examples/*.cir"))
    if argv:
        books = [b for b in books if any(a.lower() in os.path.basename(b).lower() for a in argv)]
    failures, n_plots, n_entries = [], 0, 0
    for path in books:
        cs, warnings, _ = parse_book(io.open(path, encoding="utf-8").read())
        book = os.path.basename(path)[:-4]
        for w in warnings:
            failures.append(f"{book}: parse warning: {w}")
        for i, c in enumerate(cs):
            n_entries += 1
            if not c.get("plottool"):
                continue
            n_plots += 1
            why = run_one(c)
            if why:
                failures.append(f"{book}#{i} [{c['name']}]: {why}")
    for f in failures:
        print("check_example_plots: " + f)
    print(f"check_example_plots: {'FAILED' if failures else 'ok'} -- "
          f"{n_plots} plots in {n_entries} entries, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
