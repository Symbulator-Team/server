"""
The Numerical Solver -- an interactive numerical equation solver in the
spirit of TK!Solver and SolveSys (HP48G), mounted on the main app at
/eqsheet/. ("EqSheet" was its working name; the URL and the file names
keep it as the internal handle, the way a numbered item keeps its
number, while everything a user sees says Numerical Solver.)

List of Equations: equations, one per line (# starts a comment); tick
                   the ones you want active
Variable Sheet:    mark each variable Known (value) or Unknown (guess)
Modes:             DC  -- all quantities real
                   AC  -- phasors; every equation is split into real and
                          imaginary parts, and each variable can be
                          declared Complex, Real only, or Imaginary only
Solve:             numerical root finding (SciPy) on the residuals

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

import keyword
import re

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

# The unit step, for systems handed over from a transient (TR) solve
# (#124): u(0) is 1, the practical convention for t >= 0 waveforms.
# Only joined to the namespace when the text actually *calls* u(...),
# so a plain variable named u keeps working everywhere else.
_CALLS_U = re.compile(r"\bu\s*\(")


def _step(x):
    return sp.Heaviside(x, 1)


# Python keywords, usable as plain variable names in an equation. The
# most natural name for a source current is `is`, and parse_expr reads
# through Python's own tokenizer, which refuses a bare keyword with
# "invalid syntax" (Roberto hit exactly this, 28 Aug 2026). Same cure
# as the solver's si_prefix (0.5.19, and the monograph's footnote on
# the name): a standalone keyword token is shielded behind a sentinel
# name before parsing. Unlike the solver, the sentinel is never
# unshielded inside the expression -- lambdify would have to dodge a
# keyword-named argument -- so the sentinel symbol stays internal, and
# the two helpers below translate at the API boundary instead: the
# variable names the page sees, and the knowns/guesses it sends back,
# are the plain keywords. True/False/None stay refused: those are
# literals, and a clear refusal beats quietly making symbols of them.
_SHIELDABLE = [k for k in keyword.kwlist if k not in ("True", "False", "None")]
# A keyword counts only as a standalone name: not part of a longer
# identifier, not attribute-ish, and not called like a function.
_KW_RE = re.compile(r"(?<![\w.])(" + "|".join(_SHIELDABLE) + r")(?![\w(])")
_KW_SENTINEL = "_kw_{}_zz"
_KW_BACK = re.compile(r"^_kw_(\w+)_zz$")


def _shield_keywords(text):
    return _KW_RE.sub(lambda m: _KW_SENTINEL.format(m.group(1)), text)


def _display_name(name):
    """The name the user knows: sentinel symbols read back as keywords."""
    m = _KW_BACK.match(name)
    return m.group(1) if m else name


def _internal_name(name):
    """The symbol actually inside the parsed expressions."""
    return _KW_SENTINEL.format(name) if name in _SHIELDABLE else name


def parse_side(text, mode):
    gd = ALLOWED_AC if mode == "ac" else ALLOWED
    if mode != "ac" and _CALLS_U.search(text):
        gd = dict(gd, u=_step)
    return parse_expr(_shield_keywords(text), transformations=TRANSFORMS,
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
                           "error": "each equation needs exactly one '='"})
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
            "vars": sorted(_display_name(str(s)) for s in residual.free_symbols),
            "residual": residual,
        })
    return rules, errors


def _too_long(data):
    if len(str(data.get("text", ""))) > MAX_TEXT_LEN:
        return jsonify({"ok": False,
                        "message": "that list of equations is too long"})
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
        return None, jsonify({"ok": False,
                              "message": "fix the list of equations first",
                              "errors": errors})
    selected = set(data.get("selected", []))
    active = [r for r in rules if r["line"] in selected]
    if not active:
        return None, jsonify({"ok": False, "message": "no equations selected"})
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


def _parse_restrictions(raw):
    """Per-unknown search restrictions: name -> 'pos' | 'neg' | [lo, hi].
    Returns (validated dict, error message). Anything unrecognised, or
    an absent name, means unrestricted; a range endpoint of null means
    open on that side."""
    out = {}
    for k, v in (raw or {}).items():
        if v in ("pos", "neg"):
            out[k] = v
        elif isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                lo = None if v[0] is None else float(v[0])
                hi = None if v[1] is None else float(v[1])
            except (TypeError, ValueError):
                return None, f"bad range for {k}"
            if lo is not None and hi is not None and not lo < hi:
                return None, (f"empty range for {k} — "
                              "'from' must be below 'to'")
            out[k] = (lo, hi)
    return out, None


def _restriction_bounds(restr_by_index, n, np):
    """Lower/upper bound arrays from {index: restriction}, or None when
    every entry is unrestricted. 'pos' keeps the search in [0, inf),
    'neg' in (-inf, 0], a (lo, hi) pair in [lo, hi]."""
    if not restr_by_index:
        return None
    lb = np.full(n, -np.inf)
    ub = np.full(n, np.inf)
    for i, r in restr_by_index.items():
        if r == "pos":
            lb[i] = 0.0
        elif r == "neg":
            ub[i] = 0.0
        else:
            lo, hi = r
            if lo is not None:
                lb[i] = lo
            if hi is not None:
                ub[i] = hi
    return lb, ub


def _fail_message(mode_s):
    if mode_s == "bounded":
        return ("no solution found under the restrictions — "
                "loosen them or try different guesses")
    return "did not converge — try different guesses"


def solve_dc(data, active):
    import numpy as np

    knowns = {k: float(v) for k, v in data.get("knowns", {}).items()}
    guesses = {k: float(v) for k, v in data.get("guesses", {}).items()}
    # Per-unknown search restrictions (#131).
    restrict, msg = _parse_restrictions(data.get("restrict"))
    if msg:
        return jsonify({"ok": False, "message": msg})

    needed, msg = _check_coverage(active, knowns, guesses)
    if msg:
        return jsonify({"ok": False, "message": msg})
    unknowns = sorted(needed & set(guesses))
    if not unknowns:
        return jsonify({"ok": False, "message": "no unknowns to solve for"})

    syms = [sp.Symbol(_internal_name(u)) for u in unknowns]
    subs = {sp.Symbol(_internal_name(k)): v for k, v in knowns.items()}
    residuals = [r["residual"].subs(subs) for r in active]
    try:
        fns = [sp.lambdify(syms, res, modules=["numpy"]) for res in residuals]
    except Exception as exc:
        return jsonify({"ok": False, "message": f"could not compile system: {exc}"})

    def F(x):
        return np.array([f(*x) for f in fns], dtype=float)

    x0 = np.array([guesses[u] for u in unknowns], dtype=float)
    bounds = _restriction_bounds({i: restrict[u] for i, u in enumerate(unknowns)
                                  if u in restrict}, len(unknowns), np)
    out = _run_solver(F, x0, len(active), len(unknowns), bounds)
    if isinstance(out, str):
        return jsonify({"ok": False, "message": out})
    x, ok, nfev, mode_s = out

    res_final = F(x)
    return jsonify({
        "ok": bool(ok), "mode": mode_s,
        "n_eq": len(active), "n_un": len(unknowns), "nfev": int(nfev),
        "message": "solved" if ok else _fail_message(mode_s),
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

    # Per-unknown search restrictions (#131). A restriction only means
    # something for a single real scalar, so it applies to Real only /
    # Imag only unknowns and is ignored on a Complex one (the page
    # greys it out there).
    restrict, msg = _parse_restrictions(
        {n: s.get("restrict") for n, s in unknowns_in.items()
         if s.get("domain", "complex") in ("real", "imag")})
    if msg:
        return jsonify({"ok": False, "message": msg})

    # scalar layout: for each unknown, which components are free
    layout = []          # (name, domain, index into x for re, index for im)
    x0 = []
    scalar_restr = {}    # scalar index -> restriction
    for name in unames:
        spec = unknowns_in[name]
        dom = spec.get("domain", "complex")
        ire = iim = None
        if dom in ("complex", "real"):
            ire = len(x0); x0.append(float(spec.get("re", 0) or 0))
            if dom == "real" and name in restrict:
                scalar_restr[ire] = restrict[name]
        if dom in ("complex", "imag"):
            iim = len(x0); x0.append(float(spec.get("im", 0) or 0))
            if dom == "imag" and name in restrict:
                scalar_restr[iim] = restrict[name]
        layout.append((name, dom, ire, iim))
    n_scalar = len(x0)

    syms = [sp.Symbol(_internal_name(n)) for n in unames]
    subs = {sp.Symbol(_internal_name(k)): v for k, v in knowns.items()}
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
    bounds = _restriction_bounds(scalar_restr, n_scalar, np)
    out = _run_solver(F, np.array(x0, dtype=float), n_eq_real, n_scalar, bounds)
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
        "message": "solved" if ok else _fail_message(mode_s),
        "solution": solution,
        "residuals": [{"rule": r["text"], "value": float(abs(v))}
                      for r, v in zip(active, res_final)],
    })


def _run_solver(F, x0, n_eq, n_un, bounds=None):
    """Square -> hybrid Powell root; rectangular -> least squares.

    With `bounds` (a sign-restricted solve, #131) everything goes
    through least_squares, whose trust-region method honours bounds;
    MINPACK's hybr does not take them. A square bounded system is
    judged by its residual, the same doctrine as the hybr fallback
    below: least_squares happily reports success on a boundary minimum
    that is not a root, and a root is what was asked for."""
    import numpy as np
    from scipy.optimize import root, least_squares

    def _residual_ok(x):
        r = np.abs(np.asarray(F(x), dtype=float))
        scale = max(1.0, float(np.max(np.abs(x)))) if x.size else 1.0
        return bool(r.size == 0 or float(np.max(r)) < 1e-9 * scale)

    try:
        if bounds is not None:
            lb, ub = bounds
            # A guess outside its restriction is moved to a genuinely
            # interior start rather than refused -- and never onto the
            # boundary itself: started exactly on a bound, trf nudges
            # inward by ~1e-10 and promptly reports convergence without
            # moving (measured), so an infeasible guess is placed a
            # deliberate distance inside. One-sided restrictions
            # reflect the guess's distance (at least 1) across the
            # bound; a finite range steps 10% of its width in from the
            # violated end.
            x0 = np.array(x0, dtype=float)
            for i in range(x0.size):
                lo, hi = lb[i], ub[i]
                if np.isfinite(lo) and np.isfinite(hi):
                    margin = 0.1 * (hi - lo)
                    if x0[i] <= lo:
                        x0[i] = lo + margin
                    elif x0[i] >= hi:
                        x0[i] = hi - margin
                elif np.isfinite(lo) and x0[i] <= lo:
                    x0[i] = lo + max(1.0, abs(x0[i] - lo))
                elif np.isfinite(hi) and x0[i] >= hi:
                    x0[i] = hi - max(1.0, abs(x0[i] - hi))
            sol = least_squares(F, x0, bounds=(lb, ub))
            if n_eq == n_un:
                return sol.x, _residual_ok(sol.x), sol.nfev, "bounded"
            return sol.x, sol.success, sol.nfev, "least-squares"
        if n_eq == n_un:
            sol = root(F, x0, method="hybr")
            success = bool(sol.success)
            if not success:
                # MINPACK reports "not making good progress" on systems
                # it has in fact solved exactly: a linear or explicit
                # system lands in one Newton step, and the trust-region
                # bookkeeping then sees ten iterations of no improvement
                # on a residual that is already zero. The residual is
                # the honest measure, so judge by it -- #124's TR
                # handovers are all explicit assignments and hit this
                # every time.
                r = np.abs(np.asarray(F(sol.x), dtype=float))
                scale = max(1.0, float(np.max(np.abs(sol.x)))) if sol.x.size else 1.0
                if r.size and float(np.max(r)) < 1e-9 * scale:
                    success = True
            return sol.x, success, sol.nfev, "exact"
        sol = least_squares(F, x0)
        return sol.x, sol.success, sol.nfev, "least-squares"
    except Exception as exc:
        return f"solver failed: {exc}"


@bp.get("/")
def index():
    return render_template("eqsheet.html")
