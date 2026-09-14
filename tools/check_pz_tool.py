#!/usr/bin/env python
"""The pz mini-tool: poles and zeros of a transfer function (#445).

Runs the sampler's Example 13.9 through the REAL app -- `solve_ui`, then
`mini_tool_ui("pz", ...)` on the values it hands the page -- and asserts the
poles and the zero the book prints. Then the shapes the tool exists for:

  * the transfer function as an answer over its source, `v_2/vg`: poles at
    -3000 -/+ j4000 and one zero at -5000, which is what Nilsson & Riedel
    12e prints for Example 13.9;
  * a ratio with a common factor, `(s+1)/(s^2+3*s+2)`: it cancels, so one
    pole at -2 and no zero -- solving the two polynomials separately would
    report a zero at -1 and a pole at -1 that are not there;
  * a repeated root, `1/(s+4)^2`: one root, written with its multiplicity;
  * a symbolic circuit: the roots come back as expressions in R, L and C;
  * `exp(-s)/(s+1)` and `sqrt(s)+1`, which are not ratios of polynomials,
    and `1/(r+1)`, which has no s: all three refused BY NAME (857, 858)
    rather than by a traceback out of SymPy;
  * the Rounding setting honoured, four digits against six.

Run from repos/server:

    py tools/check_pz_tool.py
    py tools/check_pz_tool.py --prove-red

`--prove-red` makes the tool read the poles off the numerator and the zeros
off the denominator, and expects the check to FAIL: a guard nobody has
watched fail is not a guard.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import symbulator_ui as ui                                    # noqa: E402

#: Example 13.9 of Nilsson & Riedel 12e, as the sampler describes it
DESC_13_9 = "e,1,0,vg:r1,1,2,1000:r2,2,3,250:l,3,0,50'm:c,2,0,1'u"
#: Example 14.6, whose elements are symbols
DESC_14_6 = "e,1,0,vi:rr,1,2,R:c,2,0,C:l,2,0,L"

FAILS = []


def check(label, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + label)
    print("        " + str(got))
    if not ok:
        print("   want " + str(want))
        FAILS.append(label)


def solve(desc):
    r = ui.solve_ui(desc, "fd", "", [], "solve", "", "", "z", [], [], [],
                    digits=4, approx=True, units=True)
    assert r.get("ok"), r
    return r["values"]


def pz(arg, values, digits=4):
    return ui.mini_tool_ui("pz", [arg], values, digits)


def rows_of(out):
    assert out.get("ok"), out
    return {r["key"]: r["plain"] for r in out["rows"]}


def refusal(out):
    """The message code of a refusal, or None if it did not refuse.

    `_err` puts the English under `error` and the coded message under
    `err`, so that a message with no code still renders (see its
    docstring). The code is what this asserts: the English is the
    translators' to change."""
    if out.get("ok"):
        return None
    return (out.get("err") or {}).get("code", out.get("error"))


def main(prove_red=False):
    if prove_red:
        import sympy as sp
        original = sp.fraction
        sp.fraction = lambda e: tuple(reversed(original(e)))
        print("prove-red: numerator and denominator swapped\n")

    values = solve(DESC_13_9)

    got = rows_of(pz("v_2/vg", values))
    check("13.9 poles of the transfer function",
          got["poles"], "-3000 - 4000j, -3000 + 4000j")
    check("13.9 zero of the transfer function", got["zeros"], "-5000")

    # the same answer named the other way round: v2 without the underscore
    check("13.9 the name spelled v2/vg",
          rows_of(pz("v2/vg", values)), got)

    got = rows_of(pz("(s+1)/(s^2+3*s+2)", values))
    check("a common factor cancels before the roots are read",
          got, {"poles": "-2", "zeros": "none"})

    got = rows_of(pz("1/(s+4)^2", values))
    check("a repeated root is one root with a multiplicity",
          got, {"poles": "-4 ×2", "zeros": "none"})

    got = rows_of(pz("v_2/vg", values, digits=6))
    check("the Rounding setting is honoured (six digits)",
          got["poles"], "-3000 - 4000j, -3000 + 4000j")

    sym = rows_of(pz("v_2/vi", solve(DESC_14_6)))
    check("a symbolic circuit gives symbolic roots",
          ("C" in sym["poles"] and "R" in sym["poles"], sym["zeros"]),
          (True, "0"))

    check("exp(-s)/(s+1) is refused by name",
          refusal(pz("exp(-s)/(s+1)", values)), ui.M_PZ_NOT_RATIONAL)
    check("sqrt(s)+1 is refused by name",
          refusal(pz("sqrt(s)+1", values)), ui.M_PZ_NOT_RATIONAL)
    check("an expression with no s is refused by name",
          refusal(pz("1/(r+1)", values)), ui.M_PZ_NEEDS_S)
    check("an empty value is refused by name",
          refusal(pz("", values)), ui.M_GIVE_A_VALUE)

    print("\n--- %d check(s) failed ---" % len(FAILS))
    for f in FAILS:
        print("   " + f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prove-red", action="store_true")
    args = ap.parse_args()
    code = main(args.prove_red)
    if args.prove_red:
        print("prove-red: the check %s, as it should"
              % ("FAILED" if code else "PASSED -- THE GUARD IS BLIND"))
        sys.exit(0 if code else 1)
    sys.exit(code)
