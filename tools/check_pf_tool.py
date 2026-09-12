#!/usr/bin/env python
"""The pf mini-tool and Evaluate's `pf(...)` against the readings the
tutorial prints (#430).

Runs Lesson 8's three power-factor circuits through the REAL app --
`solve_ui`, then `mini_tool_ui` and `evaluate_ui` on the values it hands
the page -- and asserts each reading the chapter and the example book
quote: AS7's Example 11.10 `0.97342 leading`, Practice Problem 11.10
`0.93595 lagging`, Problem 11.75 `0.99805 leading`. Then the distinctions
the tool exists for:

  * a source is read on the power it DELIVERS, an impedance on the power
    it CONSUMES, and the note under the reading says which;
  * a complex-power variable (`se`, `s_e`, `-se`) is read as given -- the
    word of the consumed power, opposite to the source's own -- and with
    no line under it, the reader knowing by then what `se` is;
  * a symbolic circuit refuses the name form and still answers the value
    form, with the symbol in it;
  * `pf(v, i)` -- the two-argument form this replaced -- is refused by
    name (853);
  * the package's own `pf()` agrees with the app on every reading.

Run from repos/server:

    py tools/check_pf_tool.py
    py tools/check_pf_tool.py --prove-red     # swaps the two conventions

`--prove-red` swaps the source and load conventions in symbulator_ui and
expects the check to FAIL: a guard nobody has watched fail is not a guard.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import symbulator_ui as ui                                   # noqa: E402

EX_1110 = "e,1,0,30:r1,1,2,6:r2,2,0,-2j:r3,2,0,4"
PP_1110 = "e,1,0,165:r1,1,2,10:r2,2,0,4j:r3,2,3,8:r4,3,0,-6j"
P_1175 = "e,1,0,240:r1,1,0,80-50j:r2,1,0,120+70j:r3,1,0,60"
P_1175C = P_1175 + ":c,1,0,x"

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'BAD'} {label}: {got!r}" + ("" if ok else f"  (want {want!r})"))
    if not ok:
        failures.append(label)


def solve(desc, omega="omega"):
    r = ui.solve_ui(desc, "ac", omega, [], "solve", "", "", "z", [], [], [],
                    digits=5, use_rms=True)
    assert r.get("ok"), r
    return r["values"]


def mini(arg, values):
    return ui.mini_tool_ui("pf", [arg], values, 5)


def evaluate(expr, values):
    return ui.evaluate_ui(expr, values, digits=5)


def reading(d):
    """plain + the note's text, or the error code, as one comparable string."""
    if not d.get("ok"):
        return f"error {d['err']['code']}"
    note = d.get("note") or {}
    return d["plain"] + (" | " + note.get("text", "") if note else "")


def main(prove_red=False):
    if prove_red:
        ui.PF_SOURCE_KINDS, ui.PF_LOAD_KINDS = "rlc", "ej"
        print("prove-red: source and load conventions swapped")

    print("Lesson 8, the three readings the chapter prints:")
    v1110 = solve(EX_1110)
    check("Example 11.10, pf e", reading(mini("e", v1110)),
          "0.97342 leading | This is the power factor for the power delivered by source `e`.")
    check("Example 11.10, Evaluate pf(e)", reading(evaluate("pf(e)", v1110)),
          "0.97342 leading | This is the power factor for the power delivered by source `e`.")
    check("Practice Problem 11.10, pf e", reading(mini("e", solve(PP_1110))),
          "0.93595 lagging | This is the power factor for the power delivered by source `e`.")
    v1175 = solve(P_1175)
    check("Problem 11.75, pf e", reading(mini("e", v1175)),
          "0.99805 leading | This is the power factor for the power delivered by source `e`.")

    print("A source on the power it delivers, an impedance on the power it consumes:")
    vload = solve("e,1,0,10:r,1,0,3+4j")
    check("e feeding 3+4j", reading(mini("e", vload)),
          "0.60000 lagging | This is the power factor for the power delivered by source `e`.")
    check("r of 3+4j", reading(mini("r", vload)),
          "0.60000 lagging | This is the power factor for the power consumed by impedance `r`.")
    check("j feeding 3+4j", reading(mini("j", solve("j,1,0,2:r,1,0,3+4j"))),
          "0.60000 lagging | This is the power factor for the power delivered by source `j`.")
    check("r2 of Example 11.10, a capacitor", reading(mini("r2", v1110)),
          "0 leading | This is the power factor for the power consumed by impedance `r2`.")
    check("r1 of Example 11.10, purely real: no word", reading(mini("r1", v1110)),
          "1.0000 | This is the power factor for the power consumed by impedance `r1`.")

    print("A complex-power variable is read as given, factor and word, no line:")
    for spelling in ("se", "s_e", "S_E"):
        # The consumed power at a source: the opposite word to `e`.
        check(f"pf {spelling}", reading(mini(spelling, v1110)), "0.97342 lagging")
    check("pf -se, the delivered power", reading(mini("-se", v1110)),
          "0.97342 leading")
    check("pf se in Evaluate", reading(evaluate("pf(se)", v1110)),
          "0.97342 lagging")
    # At the Rounding setting's five figures, padded as the Results card
    # pads -- not the two extra digits `aa` shows (Roberto, 13 Sep 2026).
    check("pf 3+4j, a bare value", reading(mini("3+4j", v1110)),
          "0.60000 lagging")
    check("pf 5, purely real: no word", reading(mini("5", v1110)), "1.0000")

    print("A symbolic circuit refuses the name and answers the value:")
    vsym = solve(P_1175C, omega="2*pi*50")
    d = mini("e", vsym)
    check("pf e with x in the circuit", reading(d), "error 854")
    check("  ...and the message names x", d["err"]["args"].get("unknown"), "x")
    d = mini("se", vsym)
    check("pf se with x in the circuit is an expression in x",
          bool(d.get("ok")) and "x" in d["plain"], True)
    check("  ...with no word and no line", (d.get("direction"), d.get("note")), ("", None))

    print("What is refused:")
    check("the old two-argument form", reading(evaluate("pf(ve, -ie)", v1110)),
          "error 853")
    check("a value of zero", reading(mini("0", v1110)), "error 856")
    check("an element kind with no convention",
          reading(mini("g1", {"v_g1": "1", "i_g1": "1"})), "error 855")

    print("The package agrees with the app:")
    import sympy as sp
    from symbulator import ac, pf
    for desc, name in ((EX_1110, "e"), (PP_1110, "e"), (P_1175, "e"),
                       ("e,1,0,10:r,1,0,3+4j", "r")):
        res = ac(desc, omega=sp.Symbol("omega"), use_rms=True)
        # The package prints five decimals as version 8 did; the app prints
        # the Rounding setting. Compare the number and the word, not the text.
        got = pf(name, res).split(": ", 1)[1].split()
        app = mini(name, solve(desc))["plain"].split()
        check(f"package pf({name!r}) on {desc[:22]}...",
              (float(got[0]), got[1:]), (float(app[0]), app[1:]))

    print()
    if failures:
        print(f"check_pf_tool: {len(failures)} FAILED")
        return 1
    print("check_pf_tool: ok")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prove-red", action="store_true")
    a = ap.parse_args()
    rc = main(a.prove_red)
    if a.prove_red:
        # Red is the pass here.
        print("prove-red:", "the check went red, as it must" if rc else
              "THE CHECK STAYED GREEN WITH THE CONVENTIONS SWAPPED")
        sys.exit(0 if rc else 1)
    sys.exit(rc)
