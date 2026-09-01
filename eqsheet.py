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
app. The page itself is templates/eqsheet.html.  The "What if..." button
after a solve opens it with ?import= carrying the solved circuit's
equation system and results -- the payload contract is documented in
tools/eqsheet_export.py, the reference implementation.

**This module knows nothing about Flask** (#208, 31 Aug 2026). It was a
Blueprint until the Numerical Solver had to run in the offline builds
too, where there is no server at all and the same code is imported by
Pyodide inside the tab. So the two entry points below, api_parse() and
api_solve(), take a plain dict and return a plain dict; eqsheet_web.py
wraps them in the Blueprint the server mounts, and repos/local's
bridge.py calls them straight. Keep it that way: an import of flask
here would break the offline build, and it would break it at boot,
silently, in a build nothing renders through Jinja.

numpy and scipy are imported inside the handlers, not at module top:
app.py's solve worker re-imports this module in every spawned child
(on platforms where multiprocessing spawns rather than forks), and the
circuit solve should not pay EqSheet's import bill. Offline that same
lateness is what keeps scipy -- 13.4 MB of wheel -- off the boot path
of a reader who never opens the Solver.
"""

import keyword
import re

import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations, convert_xor,
)

TRANSFORMS = standard_transformations + (convert_xor,)

# ---------------------------------------------------------------------
# The messages, as codes (#198)
#
# Roberto's ruling, 31 Aug 2026: the engine returns a code and its
# arguments, and the interface puts them into words. This is the 9xx
# range -- the Numerical Solver's own -- and the first of the three
# items to be built, deliberately: it is the cheapest place to find out
# whether the scheme is right, because nothing here is published to
# PyPI and no release train has to run before it can be undone.
#
# Three rules that outlive this file:
#
#   * **A code is permanent once published.** Never reused, never
#     renumbered; a retired code stays retired. Same rule as the item
#     numbers in NEXT.md, for the same reason -- someone quoting "9xx"
#     in a bug report should mean one thing forever.
#   * **Severity is a field, not a range.** A warning and an error about
#     the same thing want one code, not two.
#   * **The English stays here.** It is the generation source for
#     i18n/en.json, it is what a traceback or a bug report can quote,
#     and a second hand-kept copy in a JSON file is the drift the whole
#     scheme exists to prevent. `%{name}` slots match the argument
#     names, and are what the page's tv() fills in.
# ---------------------------------------------------------------------

M_TOO_LONG          = 901
M_FIX_EQUATIONS     = 902
M_NONE_SELECTED     = 903
M_TOO_MANY_VARS     = 904
M_UNCLASSIFIED      = 905
M_NO_UNKNOWNS       = 906
M_COMPILE_FAILED    = 907
M_BAD_RANGE         = 908
M_EMPTY_RANGE       = 909
M_SOLVER_FAILED     = 910
M_ONE_EQUALS        = 911
M_UNREADABLE        = 912
M_SOLVED            = 920
M_SOLVED_LSQ        = 921
M_SOLVED_BOUNDED    = 922
M_NO_CONVERGE       = 923
M_NO_SOLUTION_BOUND = 924

CATALOGUE = {
    M_TOO_LONG:       ("error", "that list of equations is too long"),
    M_FIX_EQUATIONS:  ("error", "fix the list of equations first"),
    M_NONE_SELECTED:  ("error", "no equations selected"),
    M_TOO_MANY_VARS:  ("error", "too many variables"),
    M_UNCLASSIFIED:   ("error", "unclassified variables: %{names}"),
    M_NO_UNKNOWNS:    ("error", "no unknowns to solve for"),
    M_COMPILE_FAILED: ("error", "could not compile system: %{error}"),
    M_BAD_RANGE:      ("error", "bad range for %{name}"),
    M_EMPTY_RANGE:    ("error", "empty range for %{name} \u2014 "
                                "'from' must be below 'to'"),
    M_SOLVER_FAILED:  ("error", "solver failed: %{error}"),
    M_ONE_EQUALS:     ("error", "each equation needs exactly one '='"),
    M_UNREADABLE:     ("error", "could not read that equation: %{error}"),
    # The status line, one sentence apiece. It used to be assembled in
    # the page from four pieces, three of which were untranslated
    # English -- which is the concrete thing this item fixes.
    M_SOLVED:         ("ok",    "solved \u2014 %{nfev} evaluations"),
    M_SOLVED_LSQ:     ("ok",    "solved (least-squares: %{n_eq} equations, "
                                "%{n_un} unknowns) \u2014 %{nfev} evaluations"),
    M_SOLVED_BOUNDED: ("ok",    "solved (restricted) \u2014 %{nfev} evaluations"),
    M_NO_CONVERGE:    ("error", "did not converge \u2014 try different guesses "
                                "(%{nfev} evaluations)"),
    M_NO_SOLUTION_BOUND: ("error",
                          "no solution found under the restrictions \u2014 "
                          "loosen them or try different guesses "
                          "(%{nfev} evaluations)"),
}


def msg(code, **args):
    """One message, as {code, args, severity, text}.

    `text` is the English, rendered here rather than in the page: it is
    what a bug report quotes and what tools/i18n.py harvests. The page
    ignores it unless it meets a code it does not know, which is what
    keeps an older page working against a newer server.
    """
    severity, template = CATALOGUE[code]
    text = template
    for k, v in args.items():
        text = text.replace("%{" + k + "}", str(v))
    return {"code": code, "args": {k: str(v) for k, v in args.items()},
            "severity": severity, "text": text}


def _fail(code, **args):
    """A refusal, in the shape every caller of this module expects."""
    return _refuse(msg(code, **args))


def _refuse(m):
    """The same, for a message a helper has already built.

    `message` is kept beside `msg` deliberately: it is the English, and
    it is what an older page, a traceback or a bug report can read
    without knowing the catalogue. The page prefers `msg` and falls back
    to it, so the two halves of a deploy can never be out of step for
    longer than the deploy itself.
    """
    return {"ok": False, "msg": m, "message": m["text"]}


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
            m = msg(M_ONE_EQUALS)
            errors.append({"line": lineno, "text": raw.strip(),
                           "msg": m, "error": m["text"]})
            continue
        lhs_s, rhs_s = line.split("=")
        try:
            lhs, rhs = parse_side(lhs_s, mode), parse_side(rhs_s, mode)
        except Exception as exc:
            # SymPy's own words ride along as an argument. They stay
            # English in every language, which is honest: they are the
            # parser's, not ours, and #198 does not pretend otherwise.
            m = msg(M_UNREADABLE, error=exc)
            errors.append({"line": lineno, "text": raw.strip(),
                           "msg": m, "error": m["text"]})
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
        return _fail(M_TOO_LONG)
    return None


def api_parse(data):
    """The page's 'Update equations': read the list of equations and
    report, per line, what it says and which variables it names."""
    err = _too_long(data)
    if err:
        return err
    rules, errors = parse_rules(data.get("text", ""), data.get("mode", "dc"))
    return {
        "rules": [{k: r[k] for k in ("line", "text", "vars")} for r in rules],
        "errors": errors,
    }


def _active_rules(data):
    rules, errors = parse_rules(data.get("text", ""), data.get("mode", "dc"))
    if errors:
        out = _fail(M_FIX_EQUATIONS)
        out["errors"] = errors
        return None, out
    selected = set(data.get("selected", []))
    active = [r for r in rules if r["line"] in selected]
    if not active:
        return None, _fail(M_NONE_SELECTED)
    return active, None


def _check_coverage(active, knowns, unknowns):
    needed = set()
    for r in active:
        needed |= set(r["vars"])
    if len(needed) > MAX_VARS:
        return None, msg(M_TOO_MANY_VARS)
    missing = needed - set(knowns) - set(unknowns)
    if missing:
        return None, msg(M_UNCLASSIFIED, names=", ".join(sorted(missing)))
    return needed, None


def api_solve(data):
    """The page's Solve: run the ticked equations against the knowns and
    the guesses, and hand back the roots."""
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
                return None, msg(M_BAD_RANGE, name=k)
            if lo is not None and hi is not None and not lo < hi:
                return None, msg(M_EMPTY_RANGE, name=k)
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


def _finite(x):
    """A float for JSON, or None when it is not a number.

    `json.dumps` writes a bare NaN or Infinity, which is Python-legal
    and **not valid JSON**: `JSON.parse` throws on it, and so does
    `Response.json()`. Found 31 Aug 2026 while porting this module to
    the offline build (#208), but it was never an offline problem --
    the hosted Solver did it too, and had since the beginning. Give it
    every variable Unknown at a guess of zero, which is exactly what
    the page starts a fresh sheet with, and a divider equation
    evaluates 0/0 at the start point; the residual came back NaN, the
    page could not read the reply at all, and the sheet sat on
    "solving..." for ever with a SyntaxError in the console and nothing
    on screen. A failed solve is a normal thing to say; saying it in
    unparseable JSON is not.

    None, not a string: the page formats these as numbers, and a
    number-shaped lie would have to be caught somewhere further in.
    """
    x = float(x)
    return x if -float("inf") < x < float("inf") else None


def _status(ok, mode_s, nfev, n_eq, n_un):
    """The whole status line, as one message.

    It used to be four pieces glued together in the page, three of them
    untranslated English (#209 found them and left them here on
    purpose). One code, one sentence, one tv() call at the other end.
    """
    if not ok:
        code = M_NO_SOLUTION_BOUND if mode_s == "bounded" else M_NO_CONVERGE
        return msg(code, nfev=nfev)
    if mode_s == "least-squares":
        return msg(M_SOLVED_LSQ, nfev=nfev, n_eq=n_eq, n_un=n_un)
    if mode_s == "bounded":
        return msg(M_SOLVED_BOUNDED, nfev=nfev)
    return msg(M_SOLVED, nfev=nfev)


def solve_dc(data, active):
    import numpy as np

    knowns = {k: float(v) for k, v in data.get("knowns", {}).items()}
    guesses = {k: float(v) for k, v in data.get("guesses", {}).items()}
    # Per-unknown search restrictions (#131).
    restrict, bad = _parse_restrictions(data.get("restrict"))
    if bad:
        return _refuse(bad)

    needed, bad = _check_coverage(active, knowns, guesses)
    if bad:
        return _refuse(bad)
    unknowns = sorted(needed & set(guesses))
    if not unknowns:
        return _fail(M_NO_UNKNOWNS)

    syms = [sp.Symbol(_internal_name(u)) for u in unknowns]
    subs = {sp.Symbol(_internal_name(k)): v for k, v in knowns.items()}
    residuals = [r["residual"].subs(subs) for r in active]
    try:
        fns = [sp.lambdify(syms, res, modules=["numpy"]) for res in residuals]
    except Exception as exc:
        return _fail(M_COMPILE_FAILED, error=exc)

    def F(x):
        return np.array([f(*x) for f in fns], dtype=float)

    x0 = np.array([guesses[u] for u in unknowns], dtype=float)
    bounds = _restriction_bounds({i: restrict[u] for i, u in enumerate(unknowns)
                                  if u in restrict}, len(unknowns), np)
    out = _run_solver(F, x0, len(active), len(unknowns), bounds)
    if isinstance(out, dict):
        return _refuse(out)
    x, ok, nfev, mode_s = out

    res_final = F(x)
    status = _status(bool(ok), mode_s, int(nfev), len(active), len(unknowns))
    return {
        "ok": bool(ok), "mode": mode_s,
        "n_eq": len(active), "n_un": len(unknowns), "nfev": int(nfev),
        "msg": status, "message": status["text"],
        "solution": {u: _finite(v) for u, v in zip(unknowns, x)},
        "residuals": [{"rule": r["text"], "value": _finite(v)}
                      for r, v in zip(active, res_final)],
    }


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

    needed, bad = _check_coverage(active, knowns, unknowns_in)
    if bad:
        return _refuse(bad)
    unames = sorted(needed & set(unknowns_in))
    if not unames:
        return _fail(M_NO_UNKNOWNS)

    # Per-unknown search restrictions (#131). A restriction only means
    # something for a single real scalar, so it applies to Real only /
    # Imag only unknowns and is ignored on a Complex one (the page
    # greys it out there).
    restrict, bad = _parse_restrictions(
        {n: s.get("restrict") for n, s in unknowns_in.items()
         if s.get("domain", "complex") in ("real", "imag")})
    if bad:
        return _refuse(bad)

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
        return _fail(M_COMPILE_FAILED, error=exc)

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
    if isinstance(out, dict):
        return _refuse(out)
    x, ok, nfev, mode_s = out

    status = _status(bool(ok), mode_s, int(nfev), n_eq_real, n_scalar)
    zsol = unpack(x)
    res_final = np.array([f(*zsol) for f in fns], dtype=complex)
    solution = {}
    for (name, dom, _, _), z in zip(layout, zsol):
        parts = {"re": _finite(z.real), "im": _finite(z.imag),
                 "mag": _finite(abs(z)),
                 "deg": _finite(np.degrees(np.angle(z)))}
        # All four or none: a phasor with a real part and no imaginary
        # part is not a partial answer, it is a broken one, and the
        # page draws it as "3 + j —".
        solution[name] = None if any(v is None for v in parts.values()) else parts
    return {
        "ok": bool(ok), "mode": mode_s,
        "n_eq": n_eq_real, "n_un": n_scalar, "nfev": int(nfev),
        "msg": status, "message": status["text"],
        "solution": solution,
        "residuals": [{"rule": r["text"], "value": _finite(abs(v))}
                      for r, v in zip(active, res_final)],
    }


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
        # A dict, not a string: the callers tell the two apart by type,
        # and a message is a dict everywhere else in this file now.
        return msg(M_SOLVER_FAILED, error=exc)

