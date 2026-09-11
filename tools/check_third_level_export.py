# -*- coding: utf-8 -*-
"""#391 -- the third level crosses to the Numerical Solver intact.

`symbulator_ui.third_level_equations` writes the defining equations for
the quantities `analysis._derived` works out *after* the KCL system is
solved: a branch voltage, a power, and the resistance or impedance a
source sees. Most of those formulas it borrows from
`engine._derived_definition`, which is the one place they are written.
The three ac powers it writes itself, because `_derived_definition`
refuses them -- `conjugate` cannot go into a symbolic stamp the linear
solver has to invert. So there is one formula in two places, and this is
what stops them drifting.

It does not compare the two pieces of source, which would only prove
they still look alike. It runs the exported equations through the
Numerical Solver -- the real `eqsheet.api_parse` and `api_solve`, the
same two calls the page makes -- and compares the sheet's answers with
the ones the solver itself returned. What is checked is the artefact.

Three things it has caught, or would:

* a formula that drifted from `_derived`;
* `conjugate(ir1)` rendered under a name the Solver's ac namespace does
  not have -- it holds `conj`, `re` and `im`. A called name outside it
  raises NameError out of `parse_expr`'s code generation, so the sheet
  refuses the line; the check sees the refusal, and the refusal would
  take every ac power with it;
* an equation that leaves the sheet non-square, or one the solver
  cannot converge on from the guesses the import hands it.

Run it directly, or let `build_local.py` run it. To watch it go red,
break a formula in `symbulator_ui.third_level_equations` -- drop the
`half`, say, or conjugate the voltage instead of the current.

    py tools/check_third_level_export.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import eqsheet                       # noqa: E402
import symbulator_ui                 # noqa: E402

TOL = 1e-7

# Circuits chosen for the shapes that produce a third level, not for
# variety: a dc divider (v_, p_, r_ on a voltage source), a current
# source (whose current is `known`, not an unknown), an ac R-L (complex
# power and the impedance seen), an ac R-C with RMS phasors (the p_/ap_
# naming switch, and a capacitor whose current is also `known`), and an
# op-amp in both domains -- the op-amp's power is measured at its output
# node, and in ac it is one of the three formulas written by hand.
CASES = [
    ("dc divider", "e1,1,0,12:r1,1,2,2'k:r2,2,0,1'k", "dc", {}),
    ("dc current source", "j1,0,1,2:r1,1,0,5", "dc", {}),
    ("dc op-amp", "e1,1,0,1:r1,1,2,1'k:o1,0,2,3:r2,2,3,10'k", "dc", {}),
    ("ac R-L", "e1,1,0,10:r1,1,2,100:l1,2,0,0.1", "ac", {"omega": "1000"}),
    ("ac R-C, RMS", "e1,1,0,10:r1,1,2,100:c1,2,0,1'u", "ac",
     {"omega": "1000", "use_rms": True}),
    ("ac op-amp", "e1,1,0,1:r1,1,2,1'k:o1,0,2,3:r2,2,3,10'k", "ac",
     {"omega": "1000"}),
]


def _payload(desc, domain, omega="0", use_rms=False):
    """The handover exactly as the page receives it."""
    out = symbulator_ui.solve_ui(desc, domain, omega, "", "solve",
                                 "", "", "", None, None, None,
                                 use_rms=use_rms)
    if not out.get("ok"):
        raise SystemExit(f"solve_ui failed: {out.get('error')}")
    if not out.get("eqsheet"):
        raise SystemExit("the solve carried no Numerical Solver payload")
    return out["eqsheet"], out["values"]


def _names(parsed):
    """Every variable the parsed sheet names, in the sheet's own
    spelling."""
    out = set()
    for r in parsed["rules"]:
        out |= set(r["vars"])
    return out


def _as_the_button_sends_it(payload, third: bool):
    """The JSON the app's `whatifPayload()` hands the Solver: the two
    lists merged or not, `third_level` dropped, and -- when merged --
    `unticked` naming the tail so the third level arrives in the List of
    Equations but switched off (#391, Roberto's second ask).

    Kept in step with `templates/index.html` by hand; what proves the two
    agree is that the sheet built from this solves to the solver's own
    answers, below."""
    p = dict(payload)
    tail = p.pop("third_level", []) or []
    if third and tail:
        base = len(p["equations"])
        p["equations"] = list(p["equations"]) + list(tail)
        p["unticked"] = [base + i for i in range(len(tail))]
    return p


def _sheet(payload, third: bool):
    """Build and solve the sheet the way the page's button does: the two
    equation lists merged or not, every equation ticked, every variable
    Unknown with its solved value as the guess -- the `?import=`
    contract's own arrival state, which is what makes this a check on the
    handover rather than on the solver.

    Returns (parsed, solved)."""
    eqs = list(payload["equations"])
    if third:
        eqs += list(payload.get("third_level") or [])
    mode = payload["mode"]
    text = "\n".join(eqs)
    parsed = eqsheet.api_parse({"text": text, "mode": mode})
    if parsed.get("errors"):
        raise AssertionError("the sheet could not parse: " + "; ".join(
            str(e.get("error")) for e in parsed["errors"]))

    results = payload["results"]
    data = {"text": text, "mode": mode,
            "selected": [r["line"] for r in parsed["rules"]]}
    if mode == "ac":
        unknowns = {}
        for name in _names(parsed):
            v = results.get(name)
            re_v, im_v = v if isinstance(v, list) else (float(v or 0.0), 0.0)
            unknowns[name] = {"domain": "complex", "re": re_v, "im": im_v}
        data["unknowns"] = unknowns
    else:
        data["guesses"] = {n: float(results.get(n) or 0.0)
                           for n in _names(parsed)}
    solved = eqsheet.api_solve(data)
    if not solved.get("ok"):
        raise AssertionError("the sheet did not solve: "
                             + str(solved.get("message") or solved))
    return parsed, solved


def _value(entry, mode):
    if mode == "ac":
        return complex(entry["re"], entry["im"])
    return float(entry)


def check_conditions() -> list:
    """#391's third part: Expert Mode's conditions cross as the Solver's
    per-unknown search restrictions, never as equations.

    Each case is a shape a reader can actually type. Two of them are
    there because they are *not* convertible and must come back empty
    rather than approximated, and one because `7 > vs > 3` -- the
    obvious spelling of a range -- is refused by the app itself, so a
    range can only ever arrive as two conditions."""
    cases = [
        (["vs > 0"], {"vs": "pos"}),
        (["0 < vs"], {"vs": "pos"}),            # written from the far end
        (["vs >= 0"], {"vs": "pos"}),
        (["vs < 0"], {"vs": "neg"}),
        (["vs > 3", "vs < 7"], {"vs": [3.0, 7.0]}),
        (["vs < 7", "vs > 3"], {"vs": [3.0, 7.0]}),      # either order
        (["vs > 3"], {"vs": [3.0, None]}),               # open at the top
        (["vs < 7"], {"vs": [None, 7.0]}),
        (["vs > 3'k"], {"vs": [3000.0, None]}),          # SI shorthand
        (["vs > 0", "vs < 7"], {"vs": [0.0, 7.0]}),      # 0 is a bound here
        (["vs > 3", "vs > 5"], {"vs": [5.0, None]}),     # tightest wins
        (["vs > 7", "vs < 3"], {}),                      # contradictory
        (["2*vs > 3"], {}),                  # not a bare name
        (["vs > ir1"], {}),                  # bound is not a number
        (["vs = 5"], {}),                    # a substitution, not a bound
        ([], {}),
    ]
    out = []
    for conds, want in cases:
        got = symbulator_ui.condition_restrictions(conds, "dc")
        if got != want:
            out.append(f"conditions {conds}: {got}, expected {want}")
    # Roberto's call: DC only. A restriction is about one real scalar and
    # every imported ac variable arrives Complex, where it is greyed out.
    if symbulator_ui.condition_restrictions(["vs > 0"], "ac"):
        out.append("conditions crossed in ac, which they must not")
    return out


def check_rounding() -> list:
    """#391's second part: a value crosses rounded to the app's own
    Rounding setting at the moment of export.

    The case that matters is the read-back. `_round_expr` hands back a
    `sp.Float` carrying `digits` digits of *precision*, so calling
    `complex()` on it turns a clean 0.3333 into 0.3333015441894531 --
    right on screen, noise in the payload. A plain "is it shorter than
    before" check would pass on that, so this asserts the exact
    decimal."""
    import sympy as sp
    third = sp.Rational(1, 3)
    cases = [(0, None), (3, 0.333), (4, 0.3333), (6, 0.333333)]
    out = []
    for digits, want in cases:
        got = symbulator_ui._round_for_export(third, digits).real
        if want is None:
            if abs(got - 1 / 3) > 1e-15:
                out.append(f"digits=0 rounded to {got!r}; it must not round")
        elif got != want:
            out.append(f"digits={digits}: {got!r}, expected exactly {want!r}")
    # Ties away from zero, not Python's ties-to-even (#318).
    if symbulator_ui._round_for_export(sp.Float("31.25"), 3).real != 31.3:
        out.append("31.25 at 3 digits is 31.3, ties away from zero")
    return out


def main() -> int:
    import sympy as sp
    failures, checked = [], 0
    for label, desc, domain, kw in CASES:
        omega = kw.get("omega", "0")
        use_rms = kw.get("use_rms", False)
        payload, values = _payload(desc, domain, omega=omega, use_rms=use_rms)
        third = payload.get("third_level") or []
        if not third:
            failures.append(f"{label}: no third-level equations exported")
            continue

        # Without the tick, nothing may change: the same equations as
        # before this item, and no third-level name in the sheet.
        plain = eqsheet.api_parse({"text": "\n".join(payload["equations"]),
                                   "mode": payload["mode"]})
        if plain.get("errors"):
            failures.append(f"{label}: the plain system stopped parsing")

        try:
            parsed, solved = _sheet(payload, third=True)
        except AssertionError as exc:
            failures.append(f"{label}: {exc}")
            continue

        # Every name in the sheet must be one the solver knows. A
        # *called* unknown name is refused by the parser above, but a
        # bare one is not: it becomes an ordinary symbol, which is how a
        # rename that half-ate a name, or an underscore that survived
        # the strip, would arrive -- as a free variable nobody notices,
        # tying nothing to the circuit.
        source = {k.replace("_", ""): v for k, v in values.items()}
        stray = _names(parsed) - set(source)
        if stray:
            failures.append(f"{label}: the sheet invented {sorted(stray)}")

        # And the third level must actually be *in* it -- an equation
        # that parsed but named nothing new would pass everything above.
        got_third = _names(parsed) - _names(
            eqsheet.api_parse({"text": "\n".join(payload["equations"]),
                               "mode": payload["mode"]}))
        if len(got_third) != len(third):
            failures.append(
                f"{label}: {len(third)} third-level equations added "
                f"{len(got_third)} variables")

        # The arrival state (#391, second ask): what the button sends must
        # untick exactly the third level and nothing else. Checked on the
        # line numbers the Solver actually keys on -- the page deselects
        # `unticked[i] + 1` -- rather than on the indices alone, since an
        # off-by-one there would untick a stamped equation and leave the
        # sheet quietly one short.
        sent = _as_the_button_sends_it(payload, third=True)
        lines_off = {i + 1 for i in sent["unticked"]}
        by_line = {r["line"]: r["text"] for r in parsed["rules"]}
        should_be_off = {ln for ln, txt in by_line.items() if txt in third}
        if lines_off != should_be_off:
            failures.append(
                f"{label}: unticked lines {sorted(lines_off)} are not the "
                f"third level's {sorted(should_be_off)}")
        if any(by_line.get(ln) in payload["equations"] for ln in lines_off):
            failures.append(f"{label}: a stamped equation arrives unticked")

        # Unticked, the sheet is the circuit alone again -- the same
        # answers as before this item, from the same equations.
        try:
            _, plain_solved = _sheet(payload, third=False)
        except AssertionError as exc:
            failures.append(f"{label}: without the tick, {exc}")
            plain_solved = None
        if plain_solved and plain_solved["n_eq"] != solved["n_eq"] - (
                len(third) * (2 if payload["mode"] == "ac" else 1)):
            failures.append(
                f"{label}: {solved['n_eq']} equations with the third level, "
                f"{plain_solved['n_eq']} without -- not a difference of "
                f"{len(third)}")

        for name, entry in solved["solution"].items():
            if name not in source or entry is None:
                continue
            try:
                want = complex(sp.N(source[name]))
            except (TypeError, ValueError):
                continue          # symbolic: nothing to compare against
            got = _value(entry, payload["mode"])
            if abs(got - want) > TOL * max(1.0, abs(want)):
                failures.append(
                    f"{label}: {name} = {got!r}, solver says {want!r}")
            checked += 1

        print(f"  {label}: {len(third)} third-level equations, "
              f"{solved['n_un']} scalar unknowns, sheet solved")

    cond = check_conditions()
    print(f"  conditions -> restrictions: "
          f"{'clean' if not cond else str(len(cond)) + ' wrong'}")
    failures += cond

    rnd = check_rounding()
    print(f"  values rounded on export: "
          f"{'clean' if not rnd else str(len(rnd)) + ' wrong'}")
    failures += rnd

    if failures:
        print("\ncheck_third_level_export: FAILED")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"check_third_level_export: clean "
          f"({len(CASES)} circuits, {checked} answers compared)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
