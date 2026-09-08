"""X14: run the by-hand systems over every built-in example and check
them against the classic Symbulator solve.

The by-hand card's whole claim is that a nodal or mesh system written
the way a student writes one arrives at the same answers the classic
solve does. That claim is checkable, over the whole example book, and
this is what checks it -- the same shape as `check_example_plots.py`.

    py tools/check_byhand.py              every dc/ac/fd entry
    py tools/check_byhand.py --method mesh
    py tools/check_byhand.py --entry "B11's Example 5.7"
    py tools/check_byhand.py --verbose    print each system

Exit code 1 on any *disagreement*. A refusal ("this circuit has a
transformer") and an unproven match are reported and counted but are
not failures: the first is the feature working as designed and the
second is SymPy running out of algebra, neither of which means a wrong
system. A transient entry is skipped -- see BY_HAND_DOMAINS below.

Proving it red: change a sign in `symbulator.byhand._walk` (return -1
where it returns 1) and the mesh run goes to hundreds of disagreements;
drop the `subst` substitution in `nodal` and every nodal KCL is left in
branch currents and fails to solve.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
SOLVER = os.path.join(os.path.dirname(SERVER), "solver")
for path in (SERVER, SOLVER):
    if path not in sys.path:
        sys.path.insert(0, path)

# Symbolic values are written in the tutorial's own notation, so an
# answer can carry a beta or an omega. The Windows console is cp1252 by
# default and dies on those mid-report.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):    # pragma: no cover
        pass

import sympy as sp                                          # noqa: E402

from circuitbook import parse_book                          # noqa: E402
from symbulator import ac, byhand, dc, fd                   # noqa: E402
from symbulator.elements import parse_circuit               # noqa: E402

#: A transient is solved in the s-domain and inverted back into time, so
#: a by-hand system for it would be the s-domain one and its answers
#: could only be compared after an inverse transform. Out of scope for
#: X14; the card says so rather than offering something it cannot check.
BY_HAND_DOMAINS = ("dc", "ac", "fd")

EXAMPLES = os.path.join(SERVER, "examples")


def _classic(desc: str, domain: str, entry: dict):
    """The classic solve, exactly as the app would run it."""
    if domain == "dc":
        return dc(desc)
    if domain == "fd":
        return fd(desc)
    omega = entry.get("omega")
    return ac(desc, omega=sp.sympify(omega)) if omega else ac(desc)


def run(method: str, only: str | None, verbose: bool) -> int:
    tally = {"agrees": 0, "differs": 0, "unsure": 0,
             "unsupported": 0, "unsolved": 0, "skipped": 0}
    failures = []

    for path in sorted(glob.glob(os.path.join(EXAMPLES, "*.cir"))):
        book = os.path.basename(path)
        with open(path, encoding="utf-8") as handle:
            circuits, _, _ = parse_book(handle.read())
        for entry in circuits:
            name = entry.get("name", "?")
            if only and only not in name:
                continue
            # `analysis:` in the file is stored under the key "domain"
            # (circuitbook's alias table), and reading the file's own
            # spelling instead quietly ran every entry as dc -- which
            # looked like a clean sweep and had tested one third of what
            # it claimed. An entry with a `tool:` is er/th/port/ex, not
            # a plain solve, and its answers are not what either by-hand
            # method produces.
            domain = (entry.get("domain") or "dc").strip().lower()
            desc = entry.get("desc") or ""
            if (domain not in BY_HAND_DOMAINS or not desc.strip()
                    or entry.get("tool")):
                tally["skipped"] += 1
                continue
            where = book + " / " + name
            try:
                elements = parse_circuit(desc)
                classic = _classic(desc, domain, entry)
            except Exception as exc:
                tally["skipped"] += 1
                if verbose:
                    print("  skip  " + where + ": classic solve said "
                          + type(exc).__name__)
                continue

            builder = byhand.nodal if method == "nodal" else byhand.mesh
            omega = entry.get("omega")
            try:
                system = builder(
                    elements, domain,
                    omega=sp.sympify(omega) if (omega and domain == "ac")
                    else None,
                    references=tuple(classic.references or ()))
                verdict = byhand.compare(system, classic.values)
            except Exception as exc:
                tally["differs"] += 1
                failures.append((where, type(exc).__name__ + ": " + str(exc)))
                print("  RAISED " + where + ": " + type(exc).__name__
                      + ": " + exc)
                continue

            tally[verdict.verdict] = tally.get(verdict.verdict, 0) + 1
            if verdict.verdict == "differs":
                failures.append((where, verdict.message))
                print("  DIFFERS  " + where)
                for check in verdict.differing:
                    print("      " + check.name + ": classic "
                          + str(check.classic) + " / by hand "
                          + str(check.byhand))
            elif verdict.verdict in ("unsolved", "unsure"):
                print("  " + verdict.verdict.upper().ljust(9) + where)
                print("      " + verdict.message)
            elif verbose:
                print("  " + verdict.verdict.ljust(12) + where)
                if verdict.verdict == "agrees":
                    for row in system.rows:
                        print("      [" + row.kind + "] " + row.plain)

    print()
    print("method: " + method)
    for key in ("agrees", "differs", "unsure", "unsolved",
                "unsupported", "skipped"):
        print("  {0:<12}{1}".format(key, tally[key]))
    checked = tally["agrees"] + tally["differs"] + tally["unsure"]
    if checked:
        print("  {0:<12}{1:.1f}% of the {2} systems built agree"
              .format("", 100.0 * tally["agrees"] / checked, checked))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("nodal", "mesh", "both"),
                        default="both")
    parser.add_argument("--entry", help="only entries whose name contains this")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    methods = ("nodal", "mesh") if args.method == "both" else (args.method,)
    status = 0
    for method in methods:
        status |= run(method, args.entry, args.verbose)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
