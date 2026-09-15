#!/usr/bin/env python
"""Mesh currents clockwise by default, and the flip (#451).

For every built-in example whose by-hand mesh system the card supports,
through the REAL app (`byhand_ui`), twice -- as it arrives and flipped:

  * neither run differs from the classic solve, and both reach the same
    verdict;
  * every mesh the drawing can place turns clockwise in the first run and
    counterclockwise in the second, read back off the drawing itself
    (`schematic.mesh_turning` on the loops the card returned);
  * each flipped mesh current is the opposite of the clockwise one.

Run from repos/server:

    py tools/check_mesh_flip.py
    py tools/check_mesh_flip.py --prove-red   # reversing does nothing

`--prove-red` replaces `byhand.reverse_meshes` with one that returns the
system unchanged and expects the check to FAIL: a guard nobody has
watched fail is not a guard.
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import sympy as sp                                            # noqa: E402

import symbulator_ui as ui                                    # noqa: E402
from circuitbook import parse_book                            # noqa: E402

EXAMPLES = HERE.parent / "examples"


def entries():
    for path in sorted(EXAMPLES.glob("*.cir")):
        circuits, _warnings, _title = parse_book(path.read_text(encoding="utf-8"))
        for i, entry in enumerate(circuits, 1):
            desc = entry.get("desc") or ""
            domain = (entry.get("analysis") or "dc").strip().lower()
            if desc and domain in ui.BYHAND_DOMAINS:
                yield "%s #%d" % (path.stem, i), desc.replace("\n", ":"), domain, \
                    entry.get("omega", "")


def run(verbose=False, only=None):
    from symbulator.schematic import mesh_turning
    checked = bad = 0
    for label, desc, domain, omega in entries():
        if only and label not in only:
            continue
        runs = {}
        for flip in (False, True):
            r = ui.byhand_ui(desc, domain, omega, "mesh", digits=0, approx=False,
                             flip=flip)
            m = (r.get("methods") or {}).get("mesh") if r.get("ok") else None
            runs[flip] = m
        if not runs[False] or not runs[False].get("supported") or not runs[False]["loops"]:
            continue
        checked += 1
        problems = []
        # What the flip can break: a system that disagrees with the
        # classic solve, or the two directions reaching different
        # verdicts. A circuit the card cannot solve either way -- coupled
        # coils in DC -- was unsolved before #451 and still is.
        if runs[True].get("verdict") != runs[False].get("verdict"):
            problems.append("verdicts differ: %s against %s flipped"
                            % (runs[False].get("verdict"), runs[True].get("verdict")))
        for flip, m in runs.items():
            if m.get("verdict") == "differs":
                problems.append("flip=%s differs from the classic solve" % flip)
            turning = mesh_turning(desc, {"loops": {k: [tuple(x) for x in v]
                                                    for k, v in m["loops"].items()}})
            wrong = [k for k, cw in turning.items() if cw == flip]
            if wrong:
                problems.append("flip=%s turning the wrong way: %s" % (flip, wrong))
        a = {x["name"]: x["value"] for x in runs[False]["answers"]}
        b = {x["name"]: x["value"] for x in runs[True]["answers"]}
        for name in runs[False]["loops"]:
            if name in a and name in b:
                try:
                    # the app's own parser: an answer may name `is`, and
                    # an AC one carries j
                    from symbulator.si_prefix import safe_sympify
                    if sp.simplify(safe_sympify(a[name]) + safe_sympify(b[name])) != 0:
                        problems.append("%s not negated: %s vs %s" % (name, a[name], b[name]))
                except Exception:                              # noqa: BLE001
                    problems.append("%s unreadable" % name)
        if problems:
            bad += 1
            print("XX %s: %s" % (label, "; ".join(problems)))
        elif verbose:
            print("ok %s" % label)
    print("\n%d mesh system(s) checked both ways, %d with a problem" % (checked, bad))
    return checked, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prove-red", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.prove_red:
        from symbulator import byhand
        byhand.reverse_meshes = lambda system, names: system
        checked, bad = run()
        print("proved red" if bad else "NOT RED: the check passed with reversal disabled")
        sys.exit(0 if bad else 1)
    checked, bad = run(args.verbose)
    print("check_mesh_flip: ok" if checked and not bad else "check_mesh_flip: FAILED")
    sys.exit(1 if bad or not checked else 0)


if __name__ == "__main__":
    main()
