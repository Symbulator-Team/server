"""
symbulator_ui -- everything the Symbulator front ends need, with no web
framework attached.

This module is shared verbatim by two front ends:

* the Flask app (`app.py`), which runs it in a killable subprocess and
  serves the results over HTTP, and
* the browser build, which loads this same file into Pyodide and calls
  it directly, with no server involved at all.

Keeping one copy is deliberate: the formatting rules, unit handling,
element ordering and variable aliasing are fiddly enough that two
implementations would drift apart within a week.

Every entry point returns a plain dict -- {"ok": True, ...} or
{"ok": False, "error": "..."} -- so it can cross a process pipe, an
HTTP response or a JavaScript boundary unchanged.
"""

from __future__ import annotations

import re


def _ok(payload):
    """Wrap a successful result as the {"ok": True, ...} dict every entry
    point returns (see the module docstring). A dict payload is merged in
    directly (its keys become top-level keys of the result); anything
    else is wrapped under a single "result" key."""
    if isinstance(payload, dict):
        return {"ok": True, **payload}
    return {"ok": True, "result": payload}


def _err(message):
    """Wrap a failure as the {"ok": False, "error": ...} dict every entry
    point returns on failure."""
    return {"ok": False, "error": message}


MAX_DESC_LEN = 2000
MAX_OMEGA_LEN = 80
MAX_VARIABLES = 40

# Everything a legitimate circuit description or omega value can contain:
# element names, node numbers, values like 1e-6 / 4.7u / 'k / 5/s / 2*v_2,
# the `[a,b,c]` parallel-impedance shortcut (expand_shorthand turns it
# into pr(a,b,c) before it ever reaches sympify), separators, and basic
# arithmetic. Deliberately excluded: { } = ; " \ ` @ # $ % & ! ? < > | ~
# and whitespace other than space.
_ALLOWED = re.compile("^[A-Za-z0-9_,.:+\\-*/()\\[\\]'^ \u00b5\u03bc]*$")
# Expert-mode equations/conditions additionally need "=".
_ALLOWED_EQ = re.compile("^[A-Za-z0-9_,.=+\\-*/()\\[\\]'^ \u00b5\u03bc]*$")
# The Solve panel's "Conditions / constraints" (solveq_ui) also allow
# < and > (and, via >=/<=, both together) -- a post-solve filter, not a
# substitution, so an actual inequality is meaningful there.
_ALLOWED_COND = re.compile("^[A-Za-z0-9_,.=<>+\\-*/()\\[\\]'^ \u00b5\u03bc]*$")
_VARNAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")
MAX_EXTRA = 20
MAX_EXTRA_LEN = 300

# Expert-mode equations/conditions are parsed the same way circuit values
# are -- imaginary units (i/I/j/J) and the calculator's apostrophe SI-unit
# shorthand (4.7'k) both work, because the engine's extra-equation/condition
# parsing already runs the same expand_shorthand()+safe_sympify() a circuit
# value goes through. What it can't do is a *bare* engineering suffix with
# no apostrophe (4.7k) the way a lone circuit field value can: that bare
# form is only ever auto-resolved when it's the *entire* field (so it can't
# accidentally rewrite part of a longer expression), and an equation is
# never just one field. So a bare suffix inside an equation/condition is
# caught here and rejected with a message pointing at the two forms that
# *are* always unambiguous, rather than left to fail deep in the solver as
# a raw sympify SyntaxError.
_BARE_SI_HINT = re.compile(
    r"(?<![\w'])\d+\.?\d*[kKMGTPmuµμnpfa](?![A-Za-z0-9_])")


def _bare_si_suffix_error(label, items):
    """None, or an error message naming the first added equation/condition
    that uses a bare SI suffix (see _BARE_SI_HINT above)."""
    for it in items:
        m = _BARE_SI_HINT.search(it)
        if m:
            tok = m.group(0)
            return (f"Added {label} {it!r} uses {tok!r} as a bare unit "
                     f"suffix, which isn't allowed here (unlike a circuit "
                     f"value field, an equation can't ask which meaning "
                     f"you intend). Write the SI-unit meaning explicitly "
                     f"with an apostrophe -- {tok[:-1]}'{tok[-1]} -- "
                     f"matching circuit syntax, or the variable meaning "
                     f"with a star -- {tok[:-1]}*{tok[-1]}.")
    return None


VALID_DOMAINS = {"dc", "ac", "fd", "tr"}


def _validate(desc: str, domain: str, omega: str, variables) -> str | None:
    """Return an error message, or None if the input looks safe and sane."""
    if not desc or not desc.strip():
        return "Please enter a circuit description."
    if len(desc) > MAX_DESC_LEN:
        return f"Circuit description too long (max {MAX_DESC_LEN} characters)."
    if not _ALLOWED.match(desc):
        return ("Circuit description contains characters that aren't used in "
                "Symbulator syntax. Allowed: letters, digits, , : . + - * / ( ) ' ^")
    if "__" in desc:
        return "Circuit description contains an invalid token."
    if domain not in VALID_DOMAINS:
        return "Unknown analysis type. Choose DC, AC, FD, or TR."
    if domain == "ac":
        if not omega or not omega.strip():
            return "AC analysis needs an angular frequency (omega)."
        if len(omega) > MAX_OMEGA_LEN or not _ALLOWED.match(omega) or "__" in omega:
            return "Omega contains invalid characters."
    if variables:
        if not isinstance(variables, list) or len(variables) > MAX_VARIABLES:
            return "Invalid variables list."
        for v in variables:
            if not isinstance(v, str) or not _VARNAME.match(v):
                return f"Invalid variable name: {v!r}"
    return None


_AND_SPLIT = re.compile(r"(?i)\s+and\s+")


def _expand_and(items):
    """Expand 'a and b' lines into separate clauses, so one line of
    added conditions can list more than one -- 'vin = 12 and pr2 = 0'
    becomes two clauses, each validated and applied on its own, rather
    than being sympify'd as a single (invalid) expression."""
    if not items:
        return items
    out = []
    for raw in items:
        out.extend(p.strip() for p in _AND_SPLIT.split(raw) if p.strip())
    return out


def _validate_extras(equations, unknowns, conditions) -> str | None:
    """Validate the expert-mode extras (lists of strings)."""
    for label, items, rx in (("equation", equations, _ALLOWED_EQ),
                             ("condition", conditions, _ALLOWED_EQ)):
        if not items:
            continue
        if len(items) > MAX_EXTRA:
            return f"Too many added {label}s (max {MAX_EXTRA})."
        for it in items:
            if (not isinstance(it, str) or len(it) > MAX_EXTRA_LEN
                    or not rx.match(it) or "__" in it):
                return f"Added {label} contains invalid characters: {it!r}"
        bare_err = _bare_si_suffix_error(label, items)
        if bare_err:
            return bare_err
    if unknowns:
        if len(unknowns) > MAX_EXTRA:
            return f"Too many added unknowns (max {MAX_EXTRA})."
        for u in unknowns:
            if not isinstance(u, str) or not _VARNAME.match(u):
                return f"Invalid unknown name: {u!r}"
    return None


# ---------------------------------------------------------------------------
# Answer formatting: rounding, decimal and SI-prefix notation
# ---------------------------------------------------------------------------

MAX_DIGITS = 15


def _clean_digits(raw) -> int:
    """Significant digits requested for the answers; 0 means 'leave the
    exact symbolic form alone', which is the default and the whole point
    of a symbolic solver."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 0
    if n < 1:
        return 0
    return min(n, MAX_DIGITS)


def _round_expr(expr, digits: int):
    """Round an answer to `digits` significant figures. Exact integers
    are left as they are -- a node sitting at exactly 36 V should read
    "36", not "36.00", even when four digits were asked for. Everything
    else (rationals, floats, and the numeric coefficients inside a
    symbolic expression) goes through sympy's N()."""
    if not digits:
        return expr
    import sympy as sp
    try:
        if expr.is_Integer:
            return expr
        return sp.N(expr, digits)
    except Exception:
        return expr


# Engineering (SI) prefixes, matching the set accepted on the input
# side so a formatted answer can be pasted straight back into a circuit.
_SI_PREFIXES = {
    18: "E", 15: "P", 12: "T", 9: "G", 6: "M", 3: "k", 0: "",
    -3: "m", -6: "u", -9: "n", -12: "p", -15: "f", -18: "a",
}
_SI_LATEX = {**_SI_PREFIXES, -6: r"\mu"}
_SI_DEFAULT_DIGITS = 4


def _approx_format(expr):
    """Force a numeric answer into decimal form: 15/2 -> 7.5, the TI's
    approximate mode. Unlike the rounding setting this imposes no digit
    count -- it uses the shortest decimal that round-trips, so 7.5 stays
    "7.5" instead of "7.50000000000000". Exact integers are left alone,
    and anything with a free symbol returns None so the caller can fall
    back to sympy's own numeric evaluation."""
    try:
        if expr.free_symbols or not expr.is_number or not expr.is_finite:
            return None
        if expr.is_Integer:
            text = str(expr)
            return text, text
        val = complex(expr)
    except Exception:
        return None

    if abs(val.imag) < 1e-30:
        text = repr(val.real)
        return text, text
    re_text, im_text = repr(val.real), repr(abs(val.imag))
    if abs(val.real) < 1e-30:
        lead = "-" if val.imag < 0 else ""
        return f"{lead}{im_text}j", f"{lead}{im_text}\\text{{j}}"
    sign = "-" if val.imag < 0 else "+"
    return (f"{re_text} {sign} {im_text}j",
            f"{re_text} {sign} {im_text}\\text{{j}}")


def _si_band(magnitude: float, digits: int):
    """Which power-of-1000 band a magnitude belongs in. Returns None if
    it falls outside the prefix range, where plain notation reads
    better."""
    import math

    if magnitude == 0 or not math.isfinite(magnitude):
        return 0
    exp3 = int(math.floor(math.log10(magnitude) / 3)) * 3
    # Rounding can tip a mantissa past 1000 (999.99 at 3 digits), which
    # belongs one band up: 1k reads better than 1000.
    if abs(float(f"%.{digits}g" % (magnitude / 10.0 ** exp3))) >= 1000:
        exp3 += 3
    if exp3 < -18 or exp3 > 18:
        return None
    return exp3


def _si_mantissa(x: float, exp3: int, digits: int):
    """Mantissa text for `x` in the given band, or None if it can't be
    written without falling back to exponent notation."""
    text = f"%.{digits}g" % (x / (10.0 ** exp3))
    return None if ("e" in text or "E" in text) else text


def _si_format(expr, digits: int, unit: str = ""):
    """SI-format a numeric answer: 0.002 -> "2m", 1234 -> "1.234k". When
    a unit is supplied the prefix attaches to it, so a current reads
    "6 mA" rather than "6m A". Complex answers (AC phasors) share one
    prefix across both parts -- "(50 - 50*I) mA" -- which is how the
    quantity would be written by hand. Returns None for anything with a
    free symbol in it: there's no meaningful prefix for an expression
    like r_b*vin/(r_a + r_b)."""
    digits = digits or _SI_DEFAULT_DIGITS
    try:
        if expr.free_symbols or not expr.is_number or not expr.is_finite:
            return None
        val = complex(expr)
    except Exception:
        return None

    is_complex = abs(val.imag) > 1e-30
    scale = max(abs(val.real), abs(val.imag)) if is_complex else abs(val.real)
    exp3 = _si_band(scale, digits)
    if exp3 is None:
        return None

    prefix, latex_prefix = _SI_PREFIXES[exp3], _SI_LATEX[exp3]
    unit_plain = f"{prefix}{_UNIT_PLAIN.get(unit, unit)}" if unit else prefix
    prefix_latex = f"\\mathrm{{{latex_prefix}}}" if prefix else ""
    unit_latex = prefix_latex + (_UNIT_LATEX.get(unit, unit) if unit else "")

    def join(body_plain, body_latex):
        """Attach the unit (plain text and LaTeX forms) to a formatted
        number, or return the number unchanged if there's no unit to
        attach -- factored out because both the real-only and complex
        branches below need to do this same last step."""
        if not unit_plain and not unit_latex:
            return body_plain, body_latex
        return (f"{body_plain} {unit_plain}".strip(),
                f"{body_latex}\\,{unit_latex}" if unit_latex else body_latex)

    if not is_complex:
        text = _si_mantissa(val.real, exp3, digits)
        return None if text is None else join(text, text)

    re_text = _si_mantissa(val.real, exp3, digits)
    im_text = _si_mantissa(abs(val.imag), exp3, digits)
    if re_text is None or im_text is None:
        return None
    if abs(val.real) < 1e-30:                       # purely imaginary
        lead = "-" if val.imag < 0 else ""
        return join(f"{lead}{im_text}j", f"{lead}{im_text}\\text{{j}}")
    sign = "-" if val.imag < 0 else "+"
    # Parenthesised so the shared prefix/unit clearly covers both parts.
    return join(f"({re_text} {sign} {im_text}j)",
                f"\\left({re_text} {sign} {im_text}\\text{{j}}\\right)")


# ---------------------------------------------------------------------------
# How the imaginary unit is shown
# ---------------------------------------------------------------------------
#
# Electrical engineering writes j, not i, because i is current. SymPy
# always prints I internally, so we convert at the display step only --
# the stored values keep SymPy's own form, which is what the evaluator
# re-reads, so a round trip can never corrupt them.
#
# The plain-text form deliberately emits the literal "5.0j" rather than
# "5.0*j": the first re-parses back to an imaginary number, the second
# comes back as a variable.

def _plain_with_j(expr) -> str:
    """str() with the imaginary unit written the engineering way."""
    import sympy as sp

    text = str(expr)
    if not expr.has(sp.I):
        return text
    # "5.0*I" -> "5.0j";  "I*x" or a lone "I" -> "1j..."
    text = re.sub(r"(?<![\w.])(\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\*I(?![\w])",
                  r"\1j", text)
    text = re.sub(r"(?<![\w.])I(?![\w])", "1j", text)
    return text


def _latex_with_j(expr) -> str:
    """LaTeX with an upright j, per IEEE house style."""
    import sympy as sp

    try:
        return sp.latex(expr, imaginary_unit="tj")
    except TypeError:            # very old sympy
        return sp.latex(expr)


# ---------------------------------------------------------------------------
# Content checks, explanatory notes, and error-message formatting
# ---------------------------------------------------------------------------

# A numeric literal written straight against the imaginary unit: 5i, 2.5J,
# .5i. The leading lookbehind keeps it off the tail of an identifier -- the
# `1i` inside `vr1i` is not a number followed by the unit -- and the trailing
# lookahead keeps it off the head of one, so `3irx` stays a name.
_IMPLICIT_IMAGINARY = re.compile(r"(?<![\w.])(\d+\.?\d*|\.\d+)([iIjJ])(?![\w])")


def normalise_imaginary(desc: str, domain: str = "ac"):
    """Rewrite every spelling of the imaginary unit into the canonical
    engineering form, so `3*i`, `3*I`, `3*J` and a bare `j` all become
    `3j` / `1j` in the description the user can see. Returns
    (new_desc, [notes]); the description is returned unchanged when
    nothing needed rewriting, so we never reformat what the user typed
    for no reason.

    i/I/j/J only mean the imaginary unit in AC (see
    `symbulator.si_prefix._allowed_namespace`), so outside AC this is a
    no-op: those letters are ordinary variable names there and nothing
    should be rewritten. `domain` defaults to "ac" so any caller that
    hasn't been updated to pass it keeps today's behaviour."""
    import sympy as sp
    from symbulator.elements import parse_circuit, _IDENTIFIER_FIELD_IDX
    from symbulator.si_prefix import safe_sympify, expand_shorthand

    if domain != "ac":
        return desc, []

    try:
        # expand_si=False: keep SI-prefix shorthand (4.7'M) as typed in
        # fields that don't need touching -- only the field(s) actually
        # being rewritten below go through a real expansion (needed for
        # safe_sympify to parse them), so a circuit like "e1,1,0,10+5*i"
        # next to "r1,1,2,4.7'k" doesn't lose the resistor's SI notation
        # just because the source needed its imaginary unit normalised.
        elements = parse_circuit(desc, expand_si=False)
    except Exception:
        return desc, []

    notes, changed = [], False
    for el in elements:
        for idx in range(len(el.fields)):
            if idx in _IDENTIFIER_FIELD_IDX.get(el.kind, ()):
                continue                      # a node or element reference
            original = el.fields[idx]
            # `10+5i` the way it is written on paper: a number against the
            # imaginary unit with no operator between them. SymPy will not
            # parse that -- it reads as one malformed literal -- so put the
            # multiplication back before anything else looks at it.
            #
            # The number must not itself be the tail of a name, which is why
            # this matches the numeric literal rather than just looking at
            # the character before the letter: in `vr1i` the `1` is preceded
            # by `r`, the lookbehind fails, and the value is left alone. A
            # letter following the unit already disqualifies it, so `3irx`
            # and `2*i_r1` are untouched either way.
            raw = _IMPLICIT_IMAGINARY.sub(r"\1*\2", original)
            if not re.search(r"(?<![\w.])[iIjJ](?![\w])", raw):
                continue
            try:
                expr = safe_sympify(expand_shorthand(raw, si=True))
            except Exception:
                continue
            if not (getattr(expr, "has", None) and expr.has(sp.I)):
                continue
            canonical = _plain_with_j(expr)
            if canonical != original:
                notes.append(f"normalised '{original}' to '{canonical}' "
                             f"in {el.name}")
                el.fields[idx] = canonical
                changed = True

    if not changed:
        return desc, []
    rebuilt = ":".join(e.name + "," + ",".join(e.fields) for e in elements)
    return rebuilt, notes


def _complex_value_error(elements, domain: str):
    """Complex component values only mean something in AC. In DC the
    values are real by definition, and FD/TR take their sources in the
    s-domain, where legitimate inputs have real coefficients and any
    complex behaviour comes from the poles of the solution. Returns an
    error message, or None.

    i/I/j/J are only reserved as the imaginary unit in AC (see
    `symbulator.si_prefix._allowed_namespace`), so outside AC they parse
    as ordinary variables and can no longer be the cause of a value
    working out complex here -- the only way to reach this now is
    genuine complex math (e.g. sqrt(-4)), so the message no longer needs
    to guess between two possible mistakes."""
    import sympy as sp
    from symbulator.si_prefix import safe_sympify, expand_value

    if domain == "ac":
        return None
    for el in elements:
        for idx in (2, 3):
            if idx >= len(el.fields) or el.kind not in ("r", "l", "c", "e", "j", "m", "t"):
                continue
            try:
                expr = safe_sympify(expand_value(el.fields[idx], "si"),
                                    reserve_imaginary=False)
            except Exception:
                continue
            if getattr(expr, "has", None) and expr.has(sp.I):
                return (
                    f"The value of '{el.name}' works out complex, and complex "
                    f"values only apply to AC analysis. Switch the analysis "
                    f"to AC, or rewrite the value so it stays real.")
    return None


def _hijack_notes(elements, reserve_imaginary: bool = True):
    """One note per name that SymPy would have reinterpreted, so the user
    learns it was read as an ordinary variable instead. `reserve_imaginary`
    should match the domain the elements were parsed for (see
    `symbulator.si_prefix.hijacked_names`) so i/I/j/J aren't reported as
    "hijacked" when they were in fact read as ordinary variables."""
    from symbulator.si_prefix import hijacked_names

    seen, notes = set(), []
    for el in elements:
        for idx in (2, 3):
            if idx >= len(el.fields):
                continue
            for name in hijacked_names(el.fields[idx], reserve_imaginary=reserve_imaginary):
                if name not in seen:
                    seen.add(name)
                    notes.append(
                        f"'{name}' was read as an ordinary variable; SymPy's "
                        f"built-in meaning was ignored.")
    return notes


def _impulse_notes(elements, domain: str):
    """FD and TR read source values in the s-domain, so a plain number is
    an impulse, not a steady level: `10` means 10·δ(t), whose value for
    every t > 0 is zero. That is correct, and it is also the single most
    confusing thing a newcomer can meet -- a 10 V source whose node
    reads 0 V. Say so rather than letting them find out."""
    if domain not in ("fd", "tr"):
        return []
    from symbulator.si_prefix import safe_sympify

    import sympy as sp

    culprits = []
    for el in elements:
        if el.kind not in ("e", "j") or len(el.fields) < 3:
            continue
        try:
            # fd/tr are never AC, so i/I/j/J are ordinary variables here.
            expr = safe_sympify(el.fields[2], reserve_imaginary=False)
        except Exception:  # noqa: BLE001
            continue
        if expr.is_number and expr != 0:
            culprits.append((el.name, sp.sstr(expr)))
    if not culprits:
        return []
    names = ", ".join(f"'{n}'" for n, _ in culprits)
    val = culprits[0][1]
    plural = "s" if len(culprits) > 1 else ""
    return [f"Source{plural} {names} took a constant s-domain value. That is "
            f"an impulse, not a steady level, so it contributes nothing for "
            f"t > 0. For a step of {val} volts (or amps) switched on at "
            f"t = 0, write {val}/s."]


# A decimal point, or genuine scientific notation (a digit glued
# directly to e/E glued to digits -- see the Circuit syntax reference's
# "Numbers, constants and the imaginary unit" section: anywhere else,
# e/E is an ordinary variable name, not scientific notation) is what
# makes SymPy read a value as an approximate float rather than an exact
# Integer/Rational the moment it's parsed.
_APPROX_NUMBER_RE = re.compile(r"\d+\.\d*|\.\d+|\d[eE][+-]?\d+")


def _has_approx_value(*texts) -> bool:
    """True if any of the given strings contains a decimal-point or
    scientific-notation numeric literal. Used to warn the user (and
    switch "exact" rounding to "approximate") when their inputs already
    contain an approximate value -- "exact" mode only skips the
    rounding step, so if the underlying number was never exact to begin
    with, "exact" mode just shows that same approximation completely
    unrounded, which looks more precise than it is rather than less."""
    for text in texts:
        if text and _APPROX_NUMBER_RE.search(text):
            return True
    return False


def _approx_value_notes(has_approx: bool) -> list:
    """One explanatory note for `_has_approx_value`, phrased for whoever
    is reading the results rather than as a bare flag -- callers that
    also auto-switch rounding to "approximate" say so in the same
    breath, so the note doubles as an explanation for why the answers
    changed shape."""
    if not has_approx:
        return []
    return ["A decimal or scientific-notation value (like 0.1 or 2e3) "
            "was found in the inputs, so the answers can't be exact -- "
            "switched \"Rounding\" from exact to approximate."]


def _exc_text(exc: Exception) -> str:
    """Human-readable text for any exception crossing the process pipe.
    Some exceptions (mpmath's ZeroDivisionError, for one) carry an empty
    message, which would otherwise reach the user as a blank error box."""
    msg = str(exc).strip()
    if not msg:
        msg = f"{type(exc).__name__} while solving (no further detail)."
    return msg[:400] + ("..." if len(msg) > 400 else "")


# Display order for the element cards: sources first (voltage, then
# current), then the passives one type at a time, then everything else.
# Python's sort is stable, so within a type the elements keep the order
# they were written in the circuit description.
_KIND_ORDER = {
    "e": 0,   # voltage sources
    "j": 1,   # current sources
    "r": 2, "l": 3, "c": 4,          # passives
    "o": 5,   # op-amps
    "t": 6,   # transformers
    "s": 7,   # short circuits
    "z": 8, "y": 8, "h": 8, "g": 8, "a": 8, "b": 8,   # two-port blocks
    "m": 9,   # mutual inductance (folded into its inductors; no card)
}


def _natural_key(name: str):
    """Sort key that orders names the way a person reads them, so e2
    comes before e10 rather than after it (which is what a plain
    alphabetical sort would do once the numbering reaches double
    digits)."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", name)]


_KIND_LABEL = {
    "r": "resistor", "l": "inductor", "c": "capacitor",
    "e": "voltage source", "j": "current source", "o": "op-amp",
    "m": "mutual inductance", "s": "short circuit", "t": "transformer",
    "z": "two-port", "y": "two-port", "h": "two-port", "g": "two-port",
    "a": "two-port", "b": "two-port",
}

# Per-element derived keys, in display order, with human labels.
_ELEMENT_KEYS = [
    ("p_{n}", "p", "power consumed", "W"),
    ("ap_{n}", "p", "average power", "W"),
    # Complex power S = V*conj(I): its magnitude is apparent power in
    # volt-amperes, its real part watts, its imaginary part reactive var.
    ("s_{n}", "s", "complex power", "VA"),
    ("z_{n}", "z", "impedance seen", "ohm"),
    ("r_{n}", "r", "resistance seen", "ohm"),
]

# Units for the special tools' named answers.
_TOOL_UNITS = {"vth": "V", "ino": "A", "req": "ohm", "zeq": "ohm",
               "pmax": "W"}
# Two-port parameter matrices carry mixed units by construction: z is
# all impedances, y all admittances, h and g are mixed, and a/b are
# dimensionless ratios mixed with the two. Rather than mislabel them,
# only the uniform ones get a unit.
_PORT_UNITS = {"z": "ohm", "y": "S"}

# Human-readable descriptions for the th/er tool's named answers, matching
# the labels the main circuit solve already gives every node voltage and
# element answer (see _ELEMENT_KEYS below) -- so the special tools stop
# being the only place that shows a bare variable name with no explanation.
_TOOL_LABELS = {
    "vth": "Thevenin voltage", "ino": "Norton current",
    "req": "Equivalent resistance", "zeq": "Equivalent impedance",
    "pmax": "Maximum deliverable power",
}

# Same idea for the two-port (port) tool: one textbook description per
# parameter position, shared across all six kinds since z11/y11/h11/g11/
# a11/b11 all play the same structural role (input, under whichever
# port-2 condition -- open or short -- defines that kind of parameter),
# just naming a different physical quantity each time.
_PORT_LABELS = {
    "z": {"11": "open-circuit input impedance",
          "12": "open-circuit reverse transfer impedance",
          "21": "open-circuit forward transfer impedance",
          "22": "open-circuit output impedance"},
    "y": {"11": "short-circuit input admittance",
          "12": "short-circuit reverse transfer admittance",
          "21": "short-circuit forward transfer admittance",
          "22": "short-circuit output admittance"},
    "h": {"11": "short-circuit input impedance",
          "12": "open-circuit reverse voltage ratio",
          "21": "short-circuit forward current gain",
          "22": "open-circuit output admittance"},
    "g": {"11": "open-circuit input admittance",
          "12": "short-circuit reverse current ratio",
          "21": "open-circuit forward voltage gain",
          "22": "short-circuit output impedance"},
    "a": {"11": "open-circuit voltage ratio",
          "12": "short-circuit transfer impedance",
          "21": "open-circuit transfer admittance",
          "22": "short-circuit current ratio"},
    "b": {"11": "open-circuit voltage ratio",
          "12": "short-circuit transfer impedance",
          "21": "open-circuit transfer admittance",
          "22": "short-circuit current ratio"},
}

_UNIT_LATEX = {"ohm": r"\Omega", "V": r"\mathrm{V}", "A": r"\mathrm{A}",
               "W": r"\mathrm{W}", "VA": r"\mathrm{VA}", "S": r"\mathrm{S}"}
_UNIT_PLAIN = {"ohm": "\u03a9"}   # plain text is UTF-8, so use the real symbol


def _with_unit(plain: str, latex: str, unit: str, show: bool):
    """Append a unit to a formatted answer. Skipped for expressions that
    still contain free symbols -- "r_b*vin/(r_a + r_b) V" would be
    wrong as often as right, since the symbols carry their own units."""
    if not show or not unit:
        return plain, latex
    return (f"{plain} {_UNIT_PLAIN.get(unit, unit)}",
            f"{latex}\\,{_UNIT_LATEX.get(unit, unit)}")


# --------------------------------------------------------------------------
# Answer names with and without the underscore
# --------------------------------------------------------------------------
#
# Symbulator 9 names its answers with an underscore between the quantity and
# the element: i_r1, v_2, p_e, r_e. Roberto's condition when that scheme was
# adopted was that the sans-underscore spelling a user naturally types --
# ir1, v2, pe, re -- must mean the same thing wherever it is given as input.
#
# It could not be done with a pattern, because the same token means different
# things in different circuits: `vx` is a free unknown unless the circuit has
# an element called x. So the alias list is built FROM the parsed circuit,
# and anything not on it is left alone. That is what keeps genuine unknowns
# working.
#
# Applied to values only -- never to a name or a node field. In `re,3,0,6`
# the name `re` must survive as the element's name; only what a value could
# refer to is rewritten.

# Every quantity the solver actually reports, per element kind. Measured by
# solving a probe circuit for each kind in both DC and AC and reading the
# keys back -- twice, because the first survey was wrong in both directions:
#
#   * it invented quantities (q, y) that do not exist, which would have put
#     phantom names like `ye` into the alias map and captured a user's own
#     unknown of that name;
#   * it dropped `ap` (apparent power) and `z` (impedance seen), which are
#     real -- they only appear in AC, and the first probe ran DC only;
#   * it assumed a mutual inductance reports something. It reports nothing.
#
# And two kinds report under a SUFFIXED name: a transformer called t answers
# as i_t2, a two-port called z1 as i_z12 and i_z13. Those are the element's
# ports, so the alias has to cover the suffixes as well as the bare name.
_NODE_QUANTITIES = ("v",)
_QUANTITIES_BY_KIND = {
    "r": ("ap", "i", "p", "s", "v"),
    "e": ("ap", "i", "p", "r", "s", "v", "z"),
    "j": ("ap", "i", "p", "r", "s", "v", "z"),
    "c": ("i", "p", "s", "v"),
    "l": ("i", "p", "s", "v"),
    "s": ("i",),                       # a short carries current, nothing else
    "o": ("ap", "i", "p", "s"),        # an op-amp reports no voltage
    "m": (),                           # mutual inductance reports nothing
    "t": ("i",),
    "z": ("i",), "y": ("i",), "h": ("i",),
    "g": ("i",), "a": ("i",), "b": ("i",),
}
# Kinds whose answers hang off numbered ports rather than the bare name.
_PORT_SUFFIXES = {"t": ("2",), "z": ("2", "3"), "y": ("2", "3"),
                  "h": ("2", "3"), "g": ("2", "3"), "a": ("2", "3"),
                  "b": ("2", "3")}
_DEFAULT_QUANTITIES = ("i", "p", "v")


def answer_aliases(elements) -> dict:
    """{sans-underscore name: underscored name} for one parsed circuit.

    Built from the circuit's own nodes and elements, so it contains exactly
    the names that could denote an answer here and nothing else."""
    from symbulator.elements import _IDENTIFIER_FIELD_IDX

    nodes, named = set(), []
    for el in elements:
        named.append((el.name, el.kind))
        for idx in _IDENTIFIER_FIELD_IDX.get(el.kind, ()):
            if idx < len(el.fields):
                nodes.add(el.fields[idx])

    alias = {}
    for node in nodes:
        for q in _NODE_QUANTITIES:
            alias[f"{q}{node}"] = f"{q}_{node}"
    for name, kind in named:
        targets = [name] + [name + sfx for sfx in _PORT_SUFFIXES.get(kind, ())]
        for q in _QUANTITIES_BY_KIND.get(kind, _DEFAULT_QUANTITIES):
            for target in targets:
                alias[f"{q}{target}"] = f"{q}_{target}"
    # A name that is already underscored is not an alias of anything.
    return {k: v for k, v in alias.items() if k != v}


def _alias_pattern(alias: dict):
    if not alias:
        return None
    # Longest first, so `ir10` wins over `ir1` when both exist.
    body = "|".join(re.escape(k) for k in sorted(alias, key=len, reverse=True))
    # Not preceded or followed by a name character, and not followed by "(" --
    # `pr(6,3)` is the parallel-resistor function, not the power in element r.
    return re.compile(rf"(?<![\w.]) ({body}) (?![\w])(?!\s*\()".replace(" ", ""))


def apply_answer_aliases(text: str, alias: dict) -> tuple:
    """Rewrite sans-underscore answer names in one value or expression.

    Returns (new_text, [names that were rewritten])."""
    pat = _alias_pattern(alias)
    if not pat or not text:
        return text, []
    used = []

    def sub(m):
        used.append(m.group(1))
        return alias[m.group(1)]

    return pat.sub(sub, text), used


# A dependent source is *supposed* to be driven by another answer, so
# `jd,0,2,.2*v1` and `ed,2,3,2*ir1` are the expected thing and say nothing.
# What is worth a word is an answer used where one is not expected -- a
# resistor whose value is `re`, the equivalent resistance seen by source e.
# That is not wrong: it describes a resistor whose value tracks that
# equivalent. It is just unusual enough to be worth asking about.
_CONTROL_KINDS = ("e", "j")          # sources may be dependent
_CONTROL_QUANTITIES = ("v", "i")     # on a voltage or a current


def ambiguous_answer_names(elements, alias: dict) -> list:
    """Answer names used as values where that is *unexpected*.

    Roberto's rule, 24 Aug 2026: a source driven by a voltage or a current
    is an ordinary dependent source and needs no comment. Anything else --
    a passive element valued by an answer, or a source driven by a power or
    an equivalent resistance -- is unusual but legal, so warn and accept.

    The message says which reading was taken, names the circuit feature
    that caused it, and gives the escape."""
    from symbulator.elements import _IDENTIFIER_FIELD_IDX
    from symbulator.si_prefix import safe_sympify, expand_shorthand

    seen, out = set(), []
    for el in elements:
        ident = _IDENTIFIER_FIELD_IDX.get(el.kind, ())
        for idx in range(len(el.fields)):
            if idx in ident:
                continue
            raw = el.fields[idx]
            # Identifiers are read from the text, not from free_symbols.
            # SymPy owns some of these names as functions -- `re` is its
            # real-part function, so safe_sympify("re") comes back with no
            # free symbols at all and the clash Roberto described would go
            # unreported. The text is the honest source for "what did the
            # user write here".
            symbols = set(re.findall(r"[A-Za-z_]\w*", raw))
            for s in sorted(symbols & set(alias)):
                quantity = s[0]
                if (el.kind in _CONTROL_KINDS
                        and quantity in _CONTROL_QUANTITIES):
                    continue          # an ordinary dependent source
                if s in seen:
                    continue
                seen.add(s)
                target = alias[s].split("_", 1)[1]
                what = {"v": "voltage", "i": "current", "p": "power",
                        "q": "reactive power", "s": "apparent power",
                        "r": "equivalent resistance",
                        "z": "equivalent impedance",
                        "y": "admittance"}.get(quantity, "answer")
                out.append(
                    f"Is that what you meant by `{s}`? This circuit has "
                    f"`{target}`, so `{s}` is its {what}, and `{el.name}` "
                    f"has been given that as its value — an element whose "
                    f"value tracks another answer. That is legal and "
                    f"sometimes deliberate, but it is unusual. If you meant "
                    f"`{s}` as an unknown of your own, rename it: `{s}x`, or "
                    f"anything not spelled like an answer.")
    return out


def prepare_inputs(desc: str, extra_equations=None, extra_unknowns=None,
                   extra_conditions=None, evaluate=None):
    """Translate every sans-underscore answer name in the user's inputs.

    Returns (desc, equations, unknowns, conditions, evaluate, notices).
    The description comes back with its values rewritten and its names and
    nodes untouched; the notices are the ambiguity warnings, if any."""
    from symbulator.elements import parse_circuit, _IDENTIFIER_FIELD_IDX

    try:
        elements = parse_circuit(desc, expand_si=False)
    except Exception:
        # Not parseable yet -- leave everything alone and let the real
        # validation report it.
        return (desc, extra_equations, extra_unknowns, extra_conditions,
                evaluate, [])

    alias = answer_aliases(elements)
    notices = ambiguous_answer_names(elements, alias)

    changed = False
    for el in elements:
        ident = _IDENTIFIER_FIELD_IDX.get(el.kind, ())
        for idx in range(len(el.fields)):
            if idx in ident:
                continue                        # a node or an element name
            new, used = apply_answer_aliases(el.fields[idx], alias)
            if used:
                el.fields[idx] = new
                changed = True
    if changed:
        desc = ":".join(e.name + "," + ",".join(e.fields) for e in elements)

    def each(items):
        if not items:
            return items
        if isinstance(items, str):
            return apply_answer_aliases(items, alias)[0]
        return [apply_answer_aliases(str(i), alias)[0] for i in items]

    return (desc, each(extra_equations), each(extra_unknowns),
            each(extra_conditions), each(evaluate), notices)


def solve_ui(desc: str, domain: str, omega: str, variables,
                  tool: str, n1: str, n2: str, kind: str,
                  extra_equations, extra_unknowns, extra_conditions,
                  digits: int = 0, si: bool = False,
                  units: bool = False, use_rms: bool = False,
                  approx: bool = False):
    """Solve a full circuit, or run the th/er/port tools. Returns
    {"ok": True, ...} with the payload grouping answers into node voltages
    and per-element results (or, for the special tools, one block of named
    answers), or {"ok": False, "error": message} on failure. Every value
    in the payload is a plain string, so it can cross a subprocess pipe
    (as app.py does) or a Pyodide/JS boundary unchanged."""
    try:
        import sympy as sp
        from symbulator import ex, tr, th, er, port
        from symbulator.elements import parse_circuit

        def fmt0(expr, unit=""):
            """Format one answer from a special tool (th/er/port) as a
            (plain-text, LaTeX) pair: SI-prefix notation first (if `si`),
            then forced-decimal (if `approx`), else the exact symbolic
            form -- with `unit` attached only when the answer is a pure
            number. Local to solve_ui() because it closes over this
            call's digits/si/approx/units flags; duplicated as `fmt`
            below (same job, different call site) rather than factored
            out, since the two evolved separately."""
            try:
                expr = sp.simplify(expr)
            except Exception:
                pass
            # A unit is only meaningful once the value is a pure number;
            # symbols in the expression carry their own units.
            has_syms = bool(getattr(expr, "free_symbols", None))
            show_unit = units and not has_syms
            if si:
                shown = _si_format(expr, digits, unit if show_unit else "")
                if shown is not None:
                    return shown
            if approx and not digits:
                shown = _approx_format(expr)
                if shown is not None:
                    return _with_unit(shown[0], shown[1], unit, show_unit)
                expr = sp.N(expr)
            expr = _round_expr(expr, digits)
            return _with_unit(_plain_with_j(expr), _latex_with_j(expr),
                              unit, show_unit)

        # Complex values are meaningful only in AC; catch them before
        # solving so the message names the element rather than surfacing
        # as a strange answer.
        _guard_elements = parse_circuit(desc)
        _bad = _complex_value_error(_guard_elements, domain)
        if _bad:
            return _err(_bad)
        _notes = _hijack_notes(_guard_elements, reserve_imaginary=(domain == "ac"))
        _notes += _impulse_notes(_guard_elements, domain)

        # "Exact" rounding only skips the rounding step -- it can't make
        # an already-approximate input exact. If a decimal or
        # scientific-notation value is anywhere in the inputs (circuit
        # description, omega, or an expert-mode equation/condition),
        # switch exact to approximate so the answers get sensibly
        # formatted instead of dumped as raw, falsely-precise floats.
        approx_forced = False
        if digits == 0 and not approx:
            omega_text = omega if domain == "ac" else ""
            if _has_approx_value(desc, omega_text,
                                  *(extra_equations or ()),
                                  *(extra_conditions or ())):
                approx = True
                approx_forced = True
                _notes += _approx_value_notes(True)

        # Expert mode: let "ir5" mean "i_r5" the same way Evaluate and
        # the Solve panel already do, by rewriting equations/conditions
        # against this circuit's real symbol names before they're parsed.
        if extra_equations or extra_conditions:
            _canon = _circuit_canonical_names(_guard_elements)
            if extra_equations:
                extra_equations = [_normalize_underscore_names(e, _canon)
                                    for e in extra_equations]
            if extra_conditions:
                extra_conditions = [_normalize_underscore_names(c, _canon)
                                     for c in extra_conditions]

        # ---- Special tools: th / er / port ------------------------------
        if tool != "solve":
            tkw = {"domain": domain}
            if domain == "ac":
                tkw["omega"] = sp.sympify(omega)
                if use_rms:
                    tkw["use_rms"] = True
            named = []          # [(display key, expr)]
            if tool == "th":
                eq = th(desc, n1, n2, **tkw)
                z_label = "req" if domain == "dc" else "zeq"
                named = [("vth", eq.vth), ("ino", eq.ino),
                         (z_label, eq.z), ("pmax", eq.pmax)]
            elif tool == "er":
                z_label = "req" if domain == "dc" else "zeq"
                named = [(z_label, er(desc, n1, n2, **tkw))]
            elif tool == "port":
                pp = port(desc, n1, n2, kind, **tkw)
                named = [(f"{kind}{ij}", pp[ij])
                         for ij in ("11", "12", "21", "22")]
            answers, flat = [], {}
            for key, expr in named:
                unit = _TOOL_UNITS.get(key, _PORT_UNITS.get(kind, "")
                                       if tool == "port" else "")
                if tool == "port":
                    label = _PORT_LABELS.get(kind, {}).get(key[len(kind):], "")
                else:
                    label = _TOOL_LABELS.get(key, "")
                plain, latex = fmt0(expr, unit)
                answers.append({"name": key, "label": label,
                                "plain": plain, "latex": latex})
                flat[key] = plain
            return _ok({"nodes": [], "elements": [], "extras": answers,
                        "values": flat, "equations": [], "notes": _notes,
                        "approx": approx, "approx_forced": approx_forced})

        # ---- Normal circuit solve (dc/ac/fd/tr) -------------------------
        kwargs = {}
        if domain == "ac":
            kwargs["omega"] = sp.sympify(omega)
            if use_rms:
                kwargs["use_rms"] = True
        if domain == "tr" and variables:
            # Accept the same casual, underscore/case-insensitive typing
            # ("v2", "V_2", "IR1") that Evaluate, Solve and the Plot key
            # already do, instead of requiring the literal solved name --
            # a name with no match passes through unchanged, so a genuine
            # typo still comes back as "nothing to report" rather than
            # being silently swallowed here.
            kwargs["variables"] = [_resolve_name(v, _guard_elements)
                                    for v in variables]
        if extra_equations:
            kwargs["equations"] = extra_equations
        if extra_unknowns:
            kwargs["unknowns"] = extra_unknowns
        if extra_conditions:
            kwargs["conditions"] = extra_conditions

        # ex() covers dc/ac/fd only -- the calculator's own prompt reads
        # "1:DC 2:AC 3:FD". Transient has always been a separate verb, so
        # call it directly.
        if domain == "tr":
            res = tr(desc, **kwargs)
        else:
            res = ex(desc, domain, **kwargs)
        values = res.values
        # 0.4.6 exposes every root; older solvers have only the one.
        solutions = list(getattr(res, "solutions", None) or [values])

        def fmt(expr, unit=""):
            """Same formatting logic as `fmt0` above, for a normal
            dc/ac/fd/tr solve's node-voltage and element answers -- see
            `fmt0`'s docstring for why these two aren't merged into one
            function."""
            try:
                expr = sp.simplify(expr)
            except Exception:
                pass
            # A unit is only meaningful once the value is a pure number;
            # symbols in the expression carry their own units.
            has_syms = bool(getattr(expr, "free_symbols", None))
            show_unit = units and not has_syms
            if si:
                shown = _si_format(expr, digits, unit if show_unit else "")
                if shown is not None:
                    return shown
            if approx and not digits:
                shown = _approx_format(expr)
                if shown is not None:
                    return _with_unit(shown[0], shown[1], unit, show_unit)
                expr = sp.N(expr)
            expr = _round_expr(expr, digits)
            return _with_unit(_plain_with_j(expr), _latex_with_j(expr),
                              unit, show_unit)

        elements = parse_circuit(desc)
        # Formatting one solution. An expert-mode equation on a power is
        # quadratic in its unknown, so a circuit can have more than one
        # answer -- both real, both satisfying every constraint. Rather than
        # pick one and present it as the answer, every solution is rendered
        # and the caller is told there is a choice. Only the values differ
        # between them; the equation system and the notes are shared.
        def render_solution(values):
            used = set()

            # ---- Tranche 1: node voltages, in order of first appearance ----
            node_order = []
            for el in elements:
                if el.kind == "m":
                    continue  # references inductor names, not nodes
                cand = [el.n1, el.n2]
                if el.kind == "o":
                    cand.append(el.fields[2])  # op-amp output node
                for n in cand:
                    if n != "0" and n not in node_order:
                        node_order.append(n)
            nodes = []
            for n in node_order:
                key = f"v_{n}"
                if key in values:
                    plain, latex = fmt(values[key], "V")
                    nodes.append({"node": n, "plain": plain, "latex": latex})
                    used.add(key)

            # ---- Tranche 2: one entry per element, in circuit order ----
            def node_v(n):
                """Node n's solved voltage, or the literal 0 for ground
                (which never gets its own v_0 entry in `values`). Used below
                to derive an element's branch voltage (v1 - v2) on the fly
                for older symbulator versions that didn't stamp a v_<name>
                answer directly."""
                if n == "0":
                    return sp.Integer(0)
                return values.get(f"v_{n}")

            element_cards = []
            for el in sorted(elements, key=lambda e: (_KIND_ORDER.get(e.kind, 99),
                                                      _natural_key(e.name))):
                items = []
                ikey = f"i_{el.name}"
                if ikey in values:
                    plain, latex = fmt(values[ikey], "A")
                    items.append({"sym": "i", "label": "current through",
                                  "plain": plain, "latex": latex})
                    used.add(ikey)
                # Voltage drop across the element: stored as v_<name> by
                # symbulator >= 0.2, else derived from the node voltages.
                if el.kind in "rlcejs":
                    vkey = f"v_{el.name}"
                    drop = values.get(vkey)
                    if drop is not None:
                        used.add(vkey)
                    else:
                        v1, v2 = node_v(el.n1), node_v(el.n2)
                        if v1 is not None and v2 is not None:
                            drop = v1 - v2
                    if drop is not None:
                        plain, latex = fmt(drop, "V")
                        items.append({"sym": "v", "label": "voltage drop",
                                      "plain": plain, "latex": latex})
                for pattern, symbol, label, unit in _ELEMENT_KEYS:
                    key = pattern.format(n=el.name)
                    if key in values:
                        plain, latex = fmt(values[key], unit)
                        items.append({"sym": symbol, "label": label,
                                      "plain": plain, "latex": latex})
                        used.add(key)
                if items:
                    element_cards.append({"name": el.name,
                                          "kind": _KIND_LABEL.get(el.kind, el.kind),
                                          "items": items})

            # ---- Safety net: anything solved but not claimed above ----
            _EXTRA_UNITS = {"v": "V", "i": "A", "p": "W", "ap": "W",
                            "s": "VA", "z": "ohm", "r": "ohm"}
            extras = []
            for key in sorted(values.keys()):
                if key not in used:
                    prefix = key.split("_", 1)[0] if "_" in key else ""
                    plain, latex = fmt(values[key], _EXTRA_UNITS.get(prefix, ""))
                    extras.append({"name": key, "plain": plain, "latex": latex})

            # ---- Flat name->expression map (for the evaluator + download).
            # Computed branch voltages are added under v_<element> (the TI
            # kept these as v<name>), unless that key already exists.
            flat = {k: str(v) for k, v in values.items()}
            for el in elements:
                if el.kind in "rlcejs":
                    key = f"v_{el.name}"
                    if key not in flat:
                        v1, v2 = node_v(el.n1), node_v(el.n2)
                        if v1 is not None and v2 is not None:
                            try:
                                flat[key] = str(sp.simplify(v1 - v2))
                            except Exception:
                                flat[key] = str(v1 - v2)
            return {"nodes": nodes, "elements": element_cards,
                    "extras": extras, "values": flat}


        # ---- The equation system the solver assembled (for download).
        equations = []
        try:
            from symbulator.engine import Circuit
            eq_domain = "fd" if domain == "tr" else domain
            circ = Circuit(elements, eq_domain,
                           omega=sp.sympify(omega) if domain == "ac" else None)
            circ.stamp_all()
            for eq in circ.equations:
                equations.append(f"{eq.lhs} = {eq.rhs}")
            for kname, kexpr in circ.known.items():
                equations.append(f"{kname} = {kexpr}")
            for extra in (extra_equations or []):
                equations.append(f"{extra}   (added)")
            for cond in (extra_conditions or []):
                equations.append(f"{cond}   (condition)")
            unk = [str(u) for u in circ.unknowns] + list(extra_unknowns or [])
            equations.append("unknowns: " + ", ".join(unk))
        except Exception:
            pass  # equations are a bonus; never fail the solve over them

        # Every solution is rendered, ranked as the solver ranked them --
        # the first is the one to show by default. The top-level nodes /
        # elements / extras / values stay as that first solution so callers
        # that predate this, and everything downstream that reads a single
        # answer, are unaffected.
        rendered = [render_solution(v) for v in solutions]
        first = rendered[0]
        return _ok({"nodes": first["nodes"], "elements": first["elements"],
                    "extras": first["extras"], "values": first["values"],
                    "solutions": rendered,
                    "equations": equations, "notes": _notes,
                    "approx": approx, "approx_forced": approx_forced})
    except Exception as exc:  # noqa: BLE001 -- anything goes back as text
        return _err(_exc_text(exc))


def _norm_name(name: str) -> str:
    """Key used to match a name the user typed against a solved answer:
    case-insensitive and underscore-optional, so `i_r1`, `i_R1`, `iR1`
    and `IR1` all collapse to the same key."""
    return name.replace("_", "").lower()


_IDENT_TOKEN = re.compile(r"[A-Za-z_]\w*")


def _circuit_canonical_names(elements):
    """Every name a solved circuit can produce: `i_<name>` for each
    element's current (every kind gets one), `v_<name>` for the branch
    voltage of "rlcejs"-kind elements (matching the same test used when
    building the flat results map), and `v_<node>` for every non-ground
    node. Used to translate an
    expert-mode equation/condition written the calculator's casual way
    ("ir5") back to the real symbol ("i_r5") before it reaches the
    solver -- see _normalize_underscore_names below."""
    names = set()
    for el in elements:
        names.add(f"i_{el.name}")
        if el.kind in "rlcejs":
            names.add(f"v_{el.name}")
        for n in (getattr(el, "n1", None), getattr(el, "n2", None)):
            if n and n != "0":
                names.add(f"v_{n}")
    return names


def _normalize_underscore_names(text, canonical):
    """Rewrite identifiers in `text` that match a canonical circuit
    symbol once case/underscores are ignored (_norm_name) to that
    symbol's real, underscored spelling -- e.g. "ir5" -> "i_r5" -- so an
    expert-mode "Add equations"/"Add conditions" line can refer to a
    circuit quantity the same casual way Evaluate and the Solve panel
    already accept (both already alias-match through _alias_mapping;
    this is the equivalent for text that gets parsed *before* any
    circuit values exist to alias against). A name with no canonical
    match -- a genuinely new symbol like an unknown resistor's value --
    passes through untouched."""
    by_norm = {}
    for n in canonical:
        by_norm.setdefault(_norm_name(n), n)

    def repl(m):
        tok = m.group(0)
        return by_norm.get(_norm_name(tok), tok)

    return _IDENT_TOKEN.sub(repl, text)


MAX_PLOT_POINTS = 2000


def _resolve_name(key: str, elements) -> str:
    """Match a casually-typed circuit quantity ("vx", "ir5") to its real
    solved name ("v_x", "i_r5"), the same underscore/case-insensitive way
    expert-mode equations do (see _normalize_underscore_names) -- used for
    a plot's variable key and for the "limit results to..." variables
    list. Falls back to the typed name unchanged if nothing matches, so
    the caller still gets a clear "not found" error instead of a silent
    substitution."""
    canonical = _circuit_canonical_names(elements)
    by_norm = {_norm_name(n): n for n in canonical}
    return by_norm.get(_norm_name(key), key)


def plot_time_ui(desc: str, key: str, t_min: float, t_max: float, n: int,
                 extra_equations, extra_unknowns, extra_conditions):
    """Sample a circuit's transient (tr()) response for `key` over
    `[t_min, t_max]`, for the "Plot vs time" tool. Returns
    {"ok": True, "t": [...], "y": [...], "key": "<resolved name>"} --
    plain lists of floats, ready for a chart -- or {"ok": False,
    "error": ...}. Every value in the payload crosses a subprocess pipe
    (app.py) or a Pyodide/JS boundary unchanged, same contract as
    solve_ui."""
    try:
        from symbulator.elements import parse_circuit
        from symbulator.plotting import time_samples, PlotError

        elements = parse_circuit(desc)
        # Plot vs time runs tr() under the hood, which is never AC.
        _notes = _hijack_notes(elements, reserve_imaginary=False)

        if extra_equations or extra_conditions:
            _canon = _circuit_canonical_names(elements)
            if extra_equations:
                extra_equations = [_normalize_underscore_names(e, _canon)
                                    for e in extra_equations]
            if extra_conditions:
                extra_conditions = [_normalize_underscore_names(c, _canon)
                                     for c in extra_conditions]
        resolved = _resolve_name(key, elements)

        t_values, y_values = time_samples(
            desc, resolved, t_max=t_max, t_min=t_min, n=n,
            equations=extra_equations or None, unknowns=extra_unknowns or None,
            conditions=extra_conditions or None)
        return _ok({"t": t_values, "y": y_values, "key": resolved, "notes": _notes})
    except PlotError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(_exc_text(exc))


def bode_ui(desc: str, key: str, f_min: float, f_max: float, n: int,
           extra_equations, extra_unknowns, extra_conditions):
    """Sample a circuit's s-domain (fd()) response for `key` across a
    frequency sweep from `f_min` to `f_max` Hz, for the "Bode plot"
    tool. Returns {"ok": True, "freq": [...], "mag_db": [...],
    "phase_deg": [...], "key": "<resolved name>"}, or {"ok": False,
    "error": ...} -- same plain-list, cross-boundary contract as
    plot_time_ui."""
    try:
        from symbulator.elements import parse_circuit
        from symbulator.plotting import bode_samples, PlotError

        elements = parse_circuit(desc)
        # Bode plot runs fd() under the hood, which is never AC.
        _notes = _hijack_notes(elements, reserve_imaginary=False)

        if extra_equations or extra_conditions:
            _canon = _circuit_canonical_names(elements)
            if extra_equations:
                extra_equations = [_normalize_underscore_names(e, _canon)
                                    for e in extra_equations]
            if extra_conditions:
                extra_conditions = [_normalize_underscore_names(c, _canon)
                                     for c in extra_conditions]
        resolved = _resolve_name(key, elements)

        freq_values, mag_db, phase_deg = bode_samples(
            desc, resolved, f_min=f_min, f_max=f_max, n=n,
            equations=extra_equations or None, unknowns=extra_unknowns or None,
            conditions=extra_conditions or None)
        return _ok({"freq": freq_values, "mag_db": mag_db, "phase_deg": phase_deg,
                    "key": resolved, "notes": _notes})
    except PlotError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(_exc_text(exc))


def _alias_mapping(values: dict, exclude=(), expr=None):
    """Map the symbols in `expr` onto the circuit's solved answers,
    ignoring case and underscores so every spelling of a name finds its
    answer. Names in `exclude` are skipped: a variable the user is
    solving *for* must stay unknown rather than being substituted away."""
    import sympy as sp

    skip = {_norm_name(str(e)) for e in exclude}

    # Normalised key -> value, but only where the key is unambiguous.
    by_norm, clashes = {}, set()
    for k, vstr in values.items():
        key = _norm_name(k)
        if key in by_norm:
            clashes.add(key)
        by_norm[key] = sp.sympify(vstr)   # internal text: parse plainly

    mapping = {}
    symbols = expr.free_symbols if expr is not None else set()
    for sym in symbols:
        key = _norm_name(str(sym))
        if key in skip or key in clashes or key not in by_norm:
            continue
        mapping[sym] = by_norm[key]
    return mapping


def _parse_equation(text: str):
    """"lhs = rhs" -> Eq(lhs, rhs); a bare expression -> Eq(expr, 0)."""
    import sympy as sp

    if "=" in text:
        lhs, rhs = text.split("=", 1)
        return sp.Eq(sp.sympify(lhs), sp.sympify(rhs))
    return sp.Eq(sp.sympify(text), 0)


def _parse_condition(text: str):
    """Parse one "Conditions / constraints" clause into a sympy relational
    -- '=' becomes an equality, the four comparisons become the matching
    sympy relational. Used to filter multiple solve() branches down to
    the physically sensible one(s), e.g. "pr1 > 0". Checked
    longest-operator-first, so ">=" and "<=" aren't misread as a bare
    ">"/"<" followed by a stray "="."""
    import sympy as sp

    ops = (
        (">=", lambda l, r: l >= r),
        ("<=", lambda l, r: l <= r),
        (">", lambda l, r: l > r),
        ("<", lambda l, r: l < r),
        ("=", sp.Eq),
    )
    for op, make in ops:
        if op in text:
            lhs, rhs = text.split(op, 1)
            return make(sp.sympify(lhs), sp.sympify(rhs))
    return sp.sympify(text)


def _conditions_hold(sol, conditions, values, wanted) -> bool:
    """True if every parsed condition holds once the solved unknowns and
    the circuit's known answers are substituted in. A condition that
    still can't be reduced to a concrete True/False (it has free symbols
    left over) is treated as satisfied -- there's nothing concrete to
    judge it against, so it isn't grounds to discard an otherwise valid
    solution."""
    import sympy as sp

    if not conditions:
        return True
    alias = _alias_mapping(values, exclude=[str(w) for w in wanted])
    for cond in conditions:
        try:
            c = cond.subs(sol).subs(alias)
            c = sp.simplify(c)
        except Exception:
            continue  # a condition that fails to evaluate isn't grounds to reject
        if c in (sp.true, True):
            continue
        if c in (sp.false, False):
            return False
    return True


def schematic_ui(desc: str):
    """Draw a circuit description as an SVG. Returns {"ok": True, "svg":
    ...} or {"ok": False, "error": message}.

    Deliberately separate from solve_ui rather than folded into it: the
    drawing is most useful on a circuit that does *not* solve yet, and
    `to_svg` parses with expand_si=False, so a bare `1k` draws where the
    solver would stop and ask which it meant. Folding it into the solve
    would mean you only ever saw a picture after a successful run, which
    is when you least need one.

    The description arrives in whichever form the page holds it -- the
    textarea uses newlines, the file format uses colons -- and both mean
    the same thing to the parser, so neither is normalised away here."""
    try:
        from symbulator.schematic import to_svg
    except ImportError:
        return _err("This build has no schematic drawer. It needs "
                    "symbulator 0.5.0 or newer.")
    if not (desc or "").strip():
        return _err("Enter a circuit first.")
    try:
        return _ok({"svg": to_svg(desc)})
    except Exception as exc:
        return _err(_exc_text(exc))


def evaluate_ui(expr_str: str, values: dict, digits: int = 0,
                 si: bool = False, approx: bool = False):
    """Evaluate a user expression against the solved values. Names match
    however they are spelled: `i_r1`, `i_R1`, `iR1` and `IR1` all find
    the same answer, since element names are lowercase by this point."""
    try:
        import sympy as sp
        from symbulator.si_prefix import safe_sympify

        parsed = safe_sympify(expr_str)
        result = parsed.subs(_alias_mapping(values, expr=parsed))
        result = sp.simplify(result)
        if si:
            shown = _si_format(result, digits)
            if shown is not None:
                return _ok({"plain": shown[0], "latex": shown[1]})
        if approx and not digits:
            shown = _approx_format(result)
            if shown is not None:
                return _ok({"plain": shown[0], "latex": shown[1]})
            result = sp.N(result)
        result = _round_expr(result, digits)
        return _ok({"plain": _plain_with_j(result),
                    "latex": _latex_with_j(result)})
    except Exception as exc:  # noqa: BLE001
        return _err(_exc_text(exc))


# Units inferred from an answer's name prefix, for labelling solved
# unknowns like "p_out" or "i_x".
_PREFIX_UNITS = {"v": "V", "i": "A", "p": "W", "ap": "W", "s": "VA",
                 "z": "ohm", "r": "ohm"}


def solveq_ui(equations, unknowns, values: dict, digits: int = 0,
                   si: bool = False, approx: bool = False,
                   units: bool = False, real_only: bool = False,
                   conditions=None):
    """Solve user equations against the circuit's answers -- the web
    counterpart of the calculator's solve()/cSolve(). Known answers are
    substituted in first, so an equation can be written directly in
    terms of v2, i_r1 and friends; anything left over is solved for.

    `real_only` is the difference between the calculator's two verbs:
    off is cSolve() (every root, complex ones included), on is solve()
    (the unknowns are declared real, so complex roots never appear).

    `conditions`: constraints ("pr1 > 0", "v1 = 12") that filter down
    which of possibly several solve() branches to keep -- sp.solve()
    happily returns every algebraic root (e.g. both signs of a squared
    term) with no way on its own to prefer the physically sensible one."""
    try:
        import sympy as sp

        wanted = [sp.Symbol(u) for u in unknowns] if unknowns else []
        parsed_eqs = [_parse_equation(e) for e in equations]
        eqs = []
        for eq in parsed_eqs:
            eqs.append(eq.subs(_alias_mapping(
                values, exclude=[str(w) for w in wanted], expr=eq)))

        if not wanted:
            # Nothing named: solve for whatever symbols remain.
            free = set()
            for eq in eqs:
                free |= eq.free_symbols
            wanted = sorted(free, key=str)
        if not wanted:
            return _err(
                "Nothing left to solve for -- every symbol in those "
                "equations already has a value. Name an unknown, or "
                "use Evaluate to compute a value instead.")

        if real_only:
            # Re-declare the unknowns as real. SymPy then solves over
            # the reals: x**2 = -1 simply has no solution, rather than
            # returning +/-j. The names are unchanged, so everything
            # downstream (units, labels) still works.
            real_map = {s: sp.Symbol(str(s), real=True) for s in wanted}
            eqs = [eq.xreplace(real_map) for eq in eqs]
            wanted = [real_map[s] for s in wanted]

        sols = sp.solve(eqs, wanted, dict=True)
        if real_only:
            # sp.solve honours the assumption for most systems, but not
            # all; drop anything that still came back complex.
            def _is_real(v):
                """True unless `v` is a concrete number whose imaginary
                part is provably nonzero. A symbolic value is always kept
                (there's nothing to judge without a number in hand); a
                numeric one is checked by simplifying its imaginary part
                to see if it's exactly 0, falling back to sympy's own
                is_real flag if that check is inconclusive."""
                if getattr(v, "free_symbols", None):
                    return True          # symbolic -- can't judge, keep it
                return sp.im(sp.nsimplify(v)) == 0 or v.is_real is not False
            sols = [s for s in sols if all(_is_real(v) for v in s.values())]

        had_sols = bool(sols)
        if conditions:
            parsed_conds = [_parse_condition(c) for c in conditions]
            sols = [s for s in sols
                    if _conditions_hold(s, parsed_conds, values, wanted)]

        if not sols:
            if conditions and had_sols:
                return _ok({"solutions": [],
                            "unknowns": [str(w) for w in wanted],
                            "notes": ["No solution satisfies the given "
                                      "conditions / constraints."]})
            if real_only:
                return _ok({"solutions": [],
                            "unknowns": [str(w) for w in wanted],
                            "notes": ["No real solution. Untick “real "
                                      "solutions only” to search the "
                                      "complex plane as well."]})
            return _ok({"solutions": [], "unknowns": [str(w) for w in wanted]})

        def render(expr, unit):
            """The same SI/approx/rounded formatting as `fmt`/`fmt0`
            above (see `fmt0`'s docstring), for one solved value of an
            equation system -- yet another copy of that same small
            formatting recipe, here because solveq_ui doesn't share a
            call frame with solve_ui."""
            try:
                expr = sp.simplify(expr)
            except Exception:
                pass
            has_syms = bool(getattr(expr, "free_symbols", None))
            show_unit = units and not has_syms
            if si:
                shown = _si_format(expr, digits, unit if show_unit else "")
                if shown is not None:
                    return shown
            if approx and not digits:
                shown = _approx_format(expr)
                if shown is not None:
                    return _with_unit(shown[0], shown[1], unit, show_unit)
                expr = sp.N(expr)
            expr = _round_expr(expr, digits)
            return _with_unit(_plain_with_j(expr), _latex_with_j(expr),
                              unit, show_unit)

        out = []
        for sol in sols:
            entry = []
            for sym in wanted:
                if sym not in sol:
                    continue
                name = str(sym)
                prefix = name.split("_", 1)[0] if "_" in name else ""
                plain, latex = render(sol[sym], _PREFIX_UNITS.get(prefix, ""))
                entry.append({"name": name, "plain": plain, "latex": latex})
            if entry:
                out.append(entry)
        return _ok({"solutions": out,
                          "unknowns": [str(w) for w in wanted]})
    except Exception as exc:  # noqa: BLE001
        return _err(_exc_text(exc))


