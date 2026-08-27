"""
EqSheet -- an interactive numerical equation solver in the spirit of
TK!Solver and SolveSys (HP48G), mounted on the main app at /eqsheet/.

Rule Sheet:     equations, one per line (# starts a comment)
Select rules:   tick the equations you want active
Variable Sheet: mark each variable Known (value) or Unknown (guess)
Modes:          DC  -- all quantities real
                AC  -- phasors; every equation is split into real and
                       imaginary parts, and each variable can be declared
                       Complex, Real only, or Imaginary only
Solve:          numerical root finding (SciPy) on the residuals

Developed standalone (Aug 2026) and handed over as a single-file Flask
app; here it is a Blueprint so the main app mounts it without a second
web app on the host. The page itself is templates/eqsheet.html. The
"What if..." button after a solve opens it with ?import= carrying the
solved circuit's equation system and results -- the payload contract is
documented in tools/eqsheet_export.py, the reference implementation.

numpy and scipy are imported inside the handlers, not at module top:
app.py's solve worker re-imports this module in every spawned child
(on platforms where multiprocessing spawns rather than forks), and the
circuit solve should not pay EqSheet's import bill.
"""

from flask import Blueprint, request, jsonify, render_template
import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations, convert_xor,
)

bp = Blueprint("eqsheet", __name__, url_prefix="/eqsheet")

TRANSFORMS = standard_transformations + (convert_xor,)

# Generous ceilings, same doctrine as MAX_DESC_LEN in app.py: these
# endpoints are public, and a runaway input should be refused before it
# reaches the parser rather than timed out inside it.
MAX_TEXT_LEN = 20000
MAX_VARS = 400

# Functions/constants the user may use in equations. Nothing else is
# exposed -- same reasoning as si_prefix.safe_sympify in the solver:
# parse against a small namespace so stray names stay ordinary symbols.
ALLOWED = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "atan2": sp.atan2,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "exp": sp.exp, "log": sp.log, "ln": sp.log, "log10": lambda x: sp.log(x, 10),
    "sqrt": sp.sqrt, "abs": sp.Abs, "Abs": sp.Abs,
    "pi": sp.pi, "e": sp.E,
    "min": sp.Min, "max": sp.Max,
    # required internally by parse_expr's code generation
    "Symbol": sp.Symbol, "Integer": sp.Integer,
    "Float": sp.Float, "Rational": sp.Rational,
}
# In AC mode, j and I are the imaginary unit (matches Symbulator's output).
ALLOWED_AC = dict(ALLOWED, j=sp.I, I=sp.I, conj=sp.conjugate, re=sp.re, im=sp.im)


def parse_side(text, mode):
    gd = ALLOWED_AC if mode == "ac" else ALLOWED
    return parse_expr(text, transformations=TRANSFORMS,
                      global_dict=gd, evaluate=True)


def parse_rules(text, mode):
    """Return (rules, errors). Each rule: {'line', 'text', 'vars', 'residual'}."""
    rules, errors = [], []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.count("=") != 1:
            errors.append({"line": lineno, "text": raw.strip(),
                           "error": "each rule needs exactly one '='"})
            continue
        lhs_s, rhs_s = line.split("=")
        try:
            lhs, rhs = parse_side(lhs_s, mode), parse_side(rhs_s, mode)
        except Exception as exc:
            errors.append({"line": lineno, "text": raw.strip(),
                           "error": str(exc)})
            continue
        residual = lhs - rhs
        rules.append({
            "line": lineno,
            "text": line,
            "vars": sorted(str(s) for s in residual.free_symbols),
            "residual": residual,
        })
    return rules, errors


def _too_long(data):
    if len(str(data.get("text", ""))) > MAX_TEXT_LEN:
        return jsonify({"ok": False, "message": "that rule sheet is too long"})
    return None


@bp.post("/api/parse")
def api_parse():
    data = request.get_json(force=True)
    err = _too_long(data)
    if err:
        return err
    rules, errors = parse_rules(data.get("text", ""), data.get("mode", "dc"))
    return jsonify({
        "rules": [{k: r[k] for k in ("line", "text", "vars")} for r in rules],
        "errors": errors,
    })


def _active_rules(data):
    rules, errors = parse_rules(data.get("text", ""), data.get("mode", "dc"))
    if errors:
        return None, jsonify({"ok": False, "message": "fix the rule sheet first",
                              "errors": errors})
    selected = set(data.get("selected", []))
    active = [r for r in rules if r["line"] in selected]
    if not active:
        return None, jsonify({"ok": False, "message": "no rules selected"})
    return active, None


def _check_coverage(active, knowns, unknowns):
    needed = set()
    for r in active:
        needed |= set(r["vars"])
    if len(needed) > MAX_VARS:
        return None, "too many variables"
    missing = needed - set(knowns) - set(unknowns)
    if missing:
        return None, "unclassified variables: " + ", ".join(sorted(missing))
    return needed, None


@bp.post("/api/solve")
def api_solve():
    data = request.get_json(force=True)
    err = _too_long(data)
    if err:
        return err
    mode = data.get("mode", "dc")
    active, err = _active_rules(data)
    if err:
        return err
    return solve_ac(data, active) if mode == "ac" else solve_dc(data, active)


def solve_dc(data, active):
    import numpy as np

    knowns = {k: float(v) for k, v in data.get("knowns", {}).items()}
    guesses = {k: float(v) for k, v in data.get("guesses", {}).items()}

    needed, msg = _check_coverage(active, knowns, guesses)
    if msg:
        return jsonify({"ok": False, "message": msg})
    unknowns = sorted(needed & set(guesses))
    if not unknowns:
        return jsonify({"ok": False, "message": "no unknowns to solve for"})

    syms = [sp.Symbol(u) for u in unknowns]
    subs = {sp.Symbol(k): v for k, v in knowns.items()}
    residuals = [r["residual"].subs(subs) for r in active]
    try:
        fns = [sp.lambdify(syms, res, modules=["numpy"]) for res in residuals]
    except Exception as exc:
        return jsonify({"ok": False, "message": f"could not compile system: {exc}"})

    def F(x):
        return np.array([f(*x) for f in fns], dtype=float)

    x0 = np.array([guesses[u] for u in unknowns], dtype=float)
    out = _run_solver(F, x0, len(active), len(unknowns))
    if isinstance(out, str):
        return jsonify({"ok": False, "message": out})
    x, ok, nfev, mode_s = out

    res_final = F(x)
    return jsonify({
        "ok": bool(ok), "mode": mode_s,
        "n_eq": len(active), "n_un": len(unknowns), "nfev": int(nfev),
        "message": "solved" if ok else "did not converge — try different guesses",
        "solution": {u: float(v) for u, v in zip(unknowns, x)},
        "residuals": [{"rule": r["text"], "value": float(v)}
                      for r, v in zip(active, res_final)],
    })


def solve_ac(data, active):
    """AC: complex residuals, each split into Re and Im. A variable's
    domain -- complex / real / imag -- decides how many scalar unknowns
    it contributes (2 / 1 / 1) and how a known value is read."""
    import numpy as np

    def as_c(d):
        return complex(float(d.get("re", 0) or 0), float(d.get("im", 0) or 0))

    knowns_in = data.get("knowns", {})     # name -> {re, im}
    unknowns_in = data.get("unknowns", {}) # name -> {domain, re, im}
    knowns = {k: as_c(v) for k, v in knowns_in.items()}

    needed, msg = _check_coverage(active, knowns, unknowns_in)
    if msg:
        return jsonify({"ok": False, "message": msg})
    unames = sorted(needed & set(unknowns_in))
    if not unames:
        return jsonify({"ok": False, "message": "no unknowns to solve for"})

    # scalar layout: for each unknown, which components are free
    layout = []          # (name, domain, index into x for re, index for im)
    x0 = []
    for name in unames:
        spec = unknowns_in[name]
        dom = spec.get("domain", "complex")
        ire = iim = None
        if dom in ("complex", "real"):
            ire = len(x0); x0.append(float(spec.get("re", 0) or 0))
        if dom in ("complex", "imag"):
            iim = len(x0); x0.append(float(spec.get("im", 0) or 0))
        layout.append((name, dom, ire, iim))
    n_scalar = len(x0)

    syms = [sp.Symbol(n) for n in unames]
    subs = {sp.Symbol(k): v for k, v in knowns.items()}
    residuals = [r["residual"].subs(subs) for r in active]
    try:
        fns = [sp.lambdify(syms, res, modules=["numpy"]) for res in residuals]
    except Exception as exc:
        return jsonify({"ok": False, "message": f"could not compile system: {exc}"})

    def unpack(x):
        vals = []
        for name, dom, ire, iim in layout:
            re_v = x[ire] if ire is not None else 0.0
            im_v = x[iim] if iim is not None else 0.0
            vals.append(complex(re_v, im_v))
        return vals

    def F(x):
        z = unpack(x)
        r = np.array([f(*z) for f in fns], dtype=complex)
        return np.concatenate([r.real, r.imag])

    n_eq_real = 2 * len(active)
    out = _run_solver(F, np.array(x0, dtype=float), n_eq_real, n_scalar)
    if isinstance(out, str):
        return jsonify({"ok": False, "message": out})
    x, ok, nfev, mode_s = out

    zsol = unpack(x)
    res_final = np.array([f(*zsol) for f in fns], dtype=complex)
    solution = {}
    for (name, dom, _, _), z in zip(layout, zsol):
        solution[name] = {"re": z.real, "im": z.imag,
                          "mag": abs(z), "deg": float(np.degrees(np.angle(z)))}
    return jsonify({
        "ok": bool(ok), "mode": mode_s,
        "n_eq": n_eq_real, "n_un": n_scalar, "nfev": int(nfev),
        "message": "solved" if ok else "did not converge — try different guesses",
        "solution": solution,
        "residuals": [{"rule": r["text"], "value": float(abs(v))}
                      for r, v in zip(active, res_final)],
    })


def _run_solver(F, x0, n_eq, n_un):
    """Square -> hybrid Powell root; rectangular -> least squares."""
    from scipy.optimize import root, least_squares
    try:
        if n_eq == n_un:
            sol = root(F, x0, method="hybr")
            return sol.x, sol.success, sol.nfev, "exact"
        sol = least_squares(F, x0)
        return sol.x, sol.success, sol.nfev, "least-squares"
    except Exception as exc:
        return f"solver failed: {exc}"


@bp.get("/")
def index():
    return render_template("eqsheet.html")
