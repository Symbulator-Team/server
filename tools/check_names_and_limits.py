#!/usr/bin/env python
"""Three things the Alexander & Sadiku sampler found the app refusing, and
the readings that prove them fixed (#450).

  1. **An element named `s`.** Its current is `is`, a Python keyword, and
     the app banned the name -- a guard written on 24 Aug 2026, four days
     before the solver learned to read a keyword as a plain name. The ban
     is lifted for every keyword the parser shields, and Evaluate's own
     parse (`_parse_with_rearrangers`) now shields them too, which it had
     never done: `is` there came back "invalid syntax".
  2. **A limit.** `limit(expression, variable, point)` in Evaluate, with
     the answers substituted first, and a Conditions line at `oo`
     (`s = oo`, `t = oo`) taken as a limit instead of a substitution that
     printed NaN for oo/oo.
  3. **A name with two digits and a letter.** `r20b` was refused as
     `r20*b`; the implicit-multiplication rule restarted its match at the
     second digit. That fix is the solver's (`si_prefix._IMPLICIT_NUM`),
     and is checked here through the app, where the reader meets it.

Everything goes through the REAL app: `solve_ui`, `evaluate_ui`,
`solveq_ui` and `byhand_ui` on the values the page holds.

Run from repos/server:

    py tools/check_names_and_limits.py
    py tools/check_names_and_limits.py --prove-red

`--prove-red` restores each old behaviour in turn, in this process, and
expects the check to FAIL for every one of them: a guard nobody has
watched fail is not a guard.
"""
import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import sympy as sp                                            # noqa: E402

import symbulator_ui as ui                                    # noqa: E402


def _solve(desc, domain="dc", omega="", tool="solve", n1="", n2="",
           digits=4, approx=True, extra=(), unknowns=()):
    # app.py and the offline bridge both validate before solving, and the
    # name ban lives there, not in solve_ui
    err = ui._validate(desc, domain, omega, None)
    if err:
        return {"ok": False, "error": err}
    return ui.solve_ui(desc, domain, omega, [], tool, n1, n2, "",
                       list(extra), list(unknowns), [], digits=digits,
                       approx=approx)


def _evaluate(desc, expr, conditions=(), domain="dc", omega="", digits=4):
    r = _solve(desc, domain, omega, digits=digits, approx=bool(digits))
    if not r.get("ok"):
        return "SOLVE FAILED: %s" % r.get("error")
    got = ui.evaluate_ui(expr, r["values"], digits=digits, approx=bool(digits),
                         domain=domain, conditions=list(conditions))
    return got.get("plain") if got.get("ok") else "ERROR: %s" % got.get("error")


def checks():
    """(label, got, want) for every reading."""
    out = []
    short = "e,1,0,V:r1,1,a,2:s,a,0:r2,1,0,4"
    r = _solve(short, digits=0, approx=False)
    out.append(("a short named s solves", bool(r.get("ok")), True))
    out.append(("Evaluate is", _evaluate(short, "is", digits=0), "V/2"))
    out.append(("Evaluate 2*is + 1", _evaluate(short, "2*is + 1", digits=0), "V + 1"))
    out.append(("Evaluate is at V = 10", _evaluate(short, "is", ["V=10"], digits=0), "5"))
    if r.get("ok"):
        sq = ui.solveq_ui(["is=5"], ["V"], r["values"], digits=0)
        got = [s["plain"] for s in (sq.get("solutions") or [[]])[0]] if sq.get("ok") else sq.get("error")
        out.append(("Solve is=5 for V", got, ["10"]))
    x = _solve(short, digits=0, approx=False, extra=["is=5"], unknowns=["V"])
    out.append(("Expert Mode is=5", [e["plain"] for e in x.get("extras", [])], ["10"]))
    bh = ui.byhand_ui(short, "dc", "", "mesh", digits=0, units=True, approx=False)
    out.append(("By-Hand mesh with s", bh.get("ok") and bh["methods"]["mesh"].get("verdict"), "agrees"))
    tr = "e,1,0,10:r2,1,a,2:r3,a,b,3:s,a,0:r6,b,0,6:l,b,0,2,2"
    out.append(("TR with s", bool(_solve(tr, "tr").get("ok")), True))
    out.append(("Lesson 4's HK5 Figure 2-29 with s",
                [e["plain"] for e in _solve("e,3,0,1.5*is:r3,3,2,3:r2,2,0,2:s,2,1",
                                            tool="er", n1="1", n2="0").get("extras", [])],
                ["0.6000"]))

    # limits
    fd = "e1,1,0,30/s:r1,1,m,1:r2,m,0,2:c,m,r,1:e2,r,0,4*ir1"   # AS7 P16.6
    out.append(("limit(s*v_m, s, oo)", _evaluate(fd, "limit(s*v_m, s, oo)", domain="fd"), "24"))
    out.append(("limit(s*v_m, s, 0)", _evaluate(fd, "limit(s*v_m, s, 0)", domain="fd"), "20"))
    out.append(("s*v_m at s = oo", _evaluate(fd, "s*v_m", ["s=oo"], domain="fd"), "24"))
    ac = "e,1,0,vi:r1,1,o,100:l,o,0,2'm:r2,o,0,100"               # AS7 P14.10
    out.append(("v_o/vi at omega = oo", _evaluate(ac, "v_o/vi", ["omega=oo"], "ac", "omega"), "0.5000"))
    step = "e1,1,0,40:r4,1,p,4:r6,p,x,6:l,x,0,5"                   # AS7 E7.13a
    out.append(("i_l at t = oo", _evaluate(step, "i_l", ["t=oo"], "tr"), "4"))
    out.append(("i_l at t = 2 unchanged", _evaluate(step, "i_l", ["t=2"], "tr"), "3.927"))
    out.append(("1/x at x = 0 unchanged", _evaluate(short, "1/x", ["x=0"]), "∞"))

    # a name with two digits and a letter
    out.append(("r20b solves", bool(_solve("e,1,0,10:r20b,1,0,20").get("ok")), True))
    out.append(("Evaluate 3*ir20b", _evaluate("e,1,0,10:r20b,1,0,20", "3*ir20b"), "1.500"))
    return out


def run(verbose=True):
    bad = 0
    for label, got, want in checks():
        ok = got == want
        bad += not ok
        if verbose or not ok:
            print("%s %-36s got %r%s" % ("ok" if ok else "XX", label, got,
                                          "" if ok else "  want %r" % (want,)))
    return bad


def prove_red():
    import symbulator.si_prefix as sip

    def old_ban():
        import keyword
        from symbulator.si_prefix import _allowed_namespace

        def names():
            owned = {n: "a Python keyword" for n in keyword.kwlist}
            for n, o in _allowed_namespace(True).items():
                if not callable(o):
                    owned.setdefault(n, "a name Symbulator reserves")
            return owned
        ui._BANNED_CACHE.clear()
        return ("_collidable_names", names)

    def old_parse():
        def parse(text, reserve_imaginary=True):
            from symbulator.si_prefix import (_allowed_namespace, _IDENT_RE,
                                              check_expression_syntax)
            check_expression_syntax(text)
            ns = _allowed_namespace(reserve_imaginary)
            used = set(_IDENT_RE.findall(text))
            for name in ui._REARRANGERS:
                if name in used:
                    ns[name] = sp.Function(name)
            for name in used:
                ns.setdefault(name, sp.Symbol(name))
            return sp.sympify(text, locals=ns)
        return ("_parse_with_rearrangers", parse)

    def old_substitute():
        return ("_substitute_conditions", lambda expr, subs_map: expr.subs(subs_map))

    def no_limit_call():
        return ("_limit_call", lambda *a, **k: None)

    def old_equality():
        return ("_equality", sp.Eq)

    patches = [old_ban, old_parse, old_substitute, no_limit_call, old_equality]
    all_red = True
    for make in patches:
        name, fn = make()
        saved = getattr(ui, name)
        setattr(ui, name, fn)
        ui._BANNED_CACHE.clear()
        try:
            bad = run(verbose=False)
        finally:
            setattr(ui, name, saved)
            ui._BANNED_CACHE.clear()
        print("-- with the old %s: %d failing %s" % (name, bad, "(red)" if bad else "(NOT RED)"))
        all_red &= bool(bad)

    saved = sip._IMPLICIT_NUM
    sip._IMPLICIT_NUM = re.compile(r"(?<![A-Za-z_])(\.?\d+\.?\d*)(?=[A-Za-z_(])")
    try:
        bad = run(verbose=False)
    finally:
        sip._IMPLICIT_NUM = saved
    print("-- with the old _IMPLICIT_NUM: %d failing %s" % (bad, "(red)" if bad else "(NOT RED)"))
    all_red &= bool(bad)
    return all_red


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prove-red", action="store_true")
    args = ap.parse_args()
    if args.prove_red:
        ok = prove_red()
        print("proved red" if ok else "A PATCH DID NOT TURN THE CHECK RED")
        sys.exit(0 if ok else 1)
    bad = run()
    print("\n%s" % ("check_names_and_limits: ok" if not bad else "%d failing" % bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
