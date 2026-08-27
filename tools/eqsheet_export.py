"""
eqsheet_export.py — bridge from symbulator (PyPI) to EqSheet.

Rebuilds the equation system the solver stamped (engine.Circuit.equations),
runs the solve, and emits EqSheet import JSON — or a ready ?import= URL.

    python eqsheet_export.py "e1,1,0,12:r1,1,2,2'k:r2,2,0,1'k"
    python eqsheet_export.py "e1,1,0,10:r1,1,2,100:l1,2,0,0.1" --domain ac --omega 1000
    python eqsheet_export.py "..." --url http://127.0.0.1:5000

DC → {"mode":"dc", results: {name: value}}
AC → {"mode":"ac", results: {name: [re, im]}}; EqSheet switches itself to
phasor mode and splits every equation into real and imaginary parts.
"""

import argparse, base64, json, sys
import sympy as sp
import symbulator as sy
from symbulator.elements import parse_circuit
from symbulator.engine import Circuit


def export(desc: str, domain: str = "dc", omega=None, suffix: str = "si") -> dict:
    elements = parse_circuit(desc)
    circ = Circuit(elements, domain, omega=omega, suffix=suffix)
    circ.stamp_all()
    # The Numerical Solver shows sans-underscore names (v1, ir1), so the
    # payload strips them -- matching symbulator_ui.solve_ui exactly.
    rename = {}
    for eq in circ.equations:
        for s in (eq.lhs.free_symbols | eq.rhs.free_symbols):
            if "_" in str(s):
                rename[s] = sp.Symbol(str(s).replace("_", ""))
    equations = [f"{sp.sstr(eq.lhs.subs(rename))} = {sp.sstr(eq.rhs.subs(rename))}"
                 for eq in circ.equations]

    if domain == "ac":
        if omega is None:
            raise SystemExit("--omega is required for --domain ac")
        res = sy.ac(desc, omega, suffix=suffix)
    else:
        res = {"dc": sy.dc, "fd": sy.fd}[domain](desc, suffix=suffix)

    results, skipped = {}, []
    for name, value in res.values.items():
        try:
            z = complex(value)
        except (TypeError, ValueError):
            skipped.append(name)          # symbolic (e.g. fd expressions)
            continue
        results[name.replace("_", "")] = \
            [z.real, z.imag] if domain == "ac" else z.real
    if skipped:
        print("skipped symbolic results:", ", ".join(skipped), file=sys.stderr)

    return {"mode": "ac" if domain == "ac" else "dc",
            "equations": equations, "results": results}


def as_url(data: dict, base: str) -> str:
    blob = base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{base.rstrip('/')}/?import={blob}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("desc", help="Symbulator circuit description")
    ap.add_argument("--domain", default="dc", choices=["dc", "ac", "fd"])
    ap.add_argument("--omega", type=float, help="angular frequency (AC)")
    ap.add_argument("--suffix", default="si", choices=["ask", "si", "var"])
    ap.add_argument("--url", help="EqSheet base URL: print an import link")
    a = ap.parse_args()
    data = export(a.desc, a.domain, a.omega, a.suffix)
    print(as_url(data, a.url) if a.url else json.dumps(data, indent=2))
