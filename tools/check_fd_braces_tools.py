#!/usr/bin/env python
"""Find equivalent reads a time value in curly brackets in FD (#458).

A plain FD solve takes `e,1,0,{480u(t)}` -- the brackets are the
calculator's shorthand for `t2s(...)`, expanded by `symbulator.fd()` on
the way in. The Find equivalent tools call `th()`, `er()` and `port()`
instead, which never expanded them, so the same description with
*Thévenin / Norton* chosen was refused: "The value '{480u(t)}' contains a
set, which is not arithmetic." Found moving NR12's Example 13.6 to the
bracketed form under the samplers' rule 33.

Runs the REAL app (`solve_ui`) and, when `repos/local` is beside this
repo, the offline bridge too, and asserts for each tool that the
bracketed description gives exactly the answers of the one written in s:

  * Thévenin / Norton on NR12's 13.6: `vth`, `ino`, `zeq`, `pmax`;
  * Resistance / impedance on the same circuit, its source killed;
  * Two-port parameters on a braced two-port circuit;
  * the brackets in an Expert Mode condition on a tool run, too;
  * outside FD the brackets are still refused, with the message that
    says why.

Run from repos/server:

    py tools/check_fd_braces_tools.py
    py tools/check_fd_braces_tools.py --prove-red   # undoes the fix

`--prove-red` stops the tool path expanding the brackets and expects the
check to FAIL: a guard nobody has watched fail is not a guard.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import symbulator_ui as ui                                   # noqa: E402

NR12_136_S = "e,1,0,480/s:r1,1,2,20:l,2,0,0.002:r2,2,a,60"
NR12_136_T = "e,1,0,{480u(t)}:r1,1,2,20:l,2,0,0.002:r2,2,a,60"
# a two-port whose drive is given in time; the parameters ignore the source
PORT_S = "e,1,0,5/s:r1,1,2,10:r2,2,0,20:l,2,3,1:r3,3,0,30"
PORT_T = "e,1,0,{5u(t)}:r1,1,2,10:r2,2,0,20:l,2,3,1:r3,3,0,30"

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": {got!r}  (want {want!r})"))
    if not ok:
        failures.append(label)


def run(desc, tool, n1, n2, kind="z", domain="fd", conditions=()):
    r = ui.solve_ui(desc, domain, "", [], tool, n1, n2, kind, [], [],
                    list(conditions), digits=0, approx=False, units=True)
    if not r.get("ok"):
        return {"error": r.get("error")}
    return {x["name"]: x.get("plain") for x in r.get("extras") or [] if isinstance(x, dict)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prove-red", action="store_true")
    args = ap.parse_args()
    if args.prove_red:
        ui._tool_desc = lambda desc, domain: desc
        print("prove-red: the tool path no longer expands the brackets")

    print("The hosted app (solve_ui):")
    for tool, n1, n2, kind, s, t in (
            ("th", "a", "0", "z", NR12_136_S, NR12_136_T),
            ("er", "a", "0", "z", NR12_136_S.replace("480/s", "0"), NR12_136_T.replace("{480u(t)}", "{0}")),
            ("port", "1", "3", "z", PORT_S, PORT_T),
            ("port", "1", "3", "h", PORT_S, PORT_T)):
        want, got = run(s, tool, n1, n2, kind), run(t, tool, n1, n2, kind)
        check(f"{tool}{'/' + kind if tool == 'port' else ''}: brackets give the answers of s "
              f"{sorted(want)}", got, want)
        check(f"{tool}: no error", "error" in got, False)

    want = run(NR12_136_S, "th", "a", "0")
    got = run(NR12_136_S.replace("480/s", "Vs"), "th", "a", "0",
              conditions=["Vs = {480u(t)}"])
    check("th: brackets in a condition too", got.get("vth"), want.get("vth"))
    # a bare number in brackets is a step: {480} and {480u(t)} are one value
    got = run(NR12_136_S.replace("480/s", "Vs"), "th", "a", "0", conditions=["Vs = {480}"])
    check("th: {480} in a condition is the step {480u(t)}", got.get("vth"), want.get("vth"))
    check("th: {480} as the source value is the step too",
          run(NR12_136_T.replace("{480u(t)}", "{480}"), "th", "a", "0").get("vth"), want.get("vth"))

    r = ui.solve_ui(NR12_136_T, "dc", "", [], "th", "a", "0", "z", [], [], [],
                    digits=0, approx=False, units=True)
    check("th in DC still refuses brackets, and says why",
          (not r.get("ok")) and "only applies in FD" in (r.get("error") or ""), True)

    local = HERE.parent.parent / "local"
    if (local / "bridge.py").exists():
        print("The offline bridge (repos/local/bridge.py):")
        sys.path.insert(0, str(local))
        import bridge

        def via_bridge(desc, tool, n1, n2, kind="z"):
            j = json.loads(bridge.solve(json.dumps(dict(
                desc=desc, domain="fd", omega="", tool=tool, n1=n1, n2=n2, kind=kind,
                digits=0, approx=False, units=True))))
            if not j.get("ok"):
                return {"error": j.get("error")}
            return {x["name"]: x.get("plain") for x in j.get("extras") or [] if isinstance(x, dict)}

        for tool, n1, n2, kind, s, t in (("th", "a", "0", "z", NR12_136_S, NR12_136_T),
                                         ("port", "1", "3", "z", PORT_S, PORT_T)):
            want, got = via_bridge(s, tool, n1, n2, kind), via_bridge(t, tool, n1, n2, kind)
            check(f"bridge {tool}: brackets give the answers of s", got, want)
            check(f"bridge {tool}: no error", "error" in got, False)
    else:
        print("(repos/local not beside this repo; the bridge is not checked)")

    if failures:
        print(f"\n{len(failures)} check(s) failed: " + ", ".join(failures))
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
