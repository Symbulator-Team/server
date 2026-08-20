"""
Symbulator Web -- a thin Flask front end over the `symbulator` package
(https://pypi.org/project/symbulator/).

Design notes:

- The actual solving runs in a separate, killable child process with a
  hard timeout. Symbolic solving can run essentially forever on
  pathological inputs, and on a public site anyone can type anything
  into the box; a timeout on the request thread alone wouldn't stop the
  underlying computation, so the child process is terminated outright.

- Input is validated *before* it ever reaches SymPy. Circuit values are
  parsed with sympy.sympify, which is an expression evaluator -- so the
  web layer restricts the character set (no brackets, braces, equals,
  quotes, backslashes...) and rejects double underscores, which closes
  off the classic sympify attack surface (attribute access / dunder
  tricks). Lengths are capped so nobody submits a megabyte of "circuit".

- WSGI throughout (Flask + gunicorn on Render, Passenger on cPanel
  later) -- see DEPLOY.md.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import re
import time

from flask import Flask, jsonify, render_template, request

from circuitbook import parse_book

app = Flask(__name__)

# Uploaded circuit books are plain text; half a megabyte is far more
# than any realistic file and keeps a hostile upload from filling RAM.
MAX_UPLOAD_BYTES = 512 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

EXAMPLES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "examples.sym")

# ---------------------------------------------------------------------------
# Limits and validation
# ---------------------------------------------------------------------------

SOLVE_TIMEOUT_S = float(os.environ.get("SYMBULATOR_TIMEOUT", "25"))

# Everything below the HTTP layer lives in symbulator_ui, which the
# browser build loads into Pyodide unchanged. This file is only the web
# server around it: validation is re-used from there, and the actual
# solving runs in a killable child process.
from symbulator_ui import (                                   # noqa: E402
    solve_ui, evaluate_ui, solveq_ui, normalise_imaginary,
    plot_time_ui, bode_ui,
    _validate, _validate_extras, _expand_and, _clean_digits, _exc_text,
    _ALLOWED, _ALLOWED_EQ, _ALLOWED_COND, _VARNAME,
    MAX_DESC_LEN, MAX_OMEGA_LEN, MAX_VARIABLES, MAX_EXTRA, MAX_EXTRA_LEN,
    MAX_PLOT_POINTS, VALID_DOMAINS,
)


def _call_worker(conn, fn_name, args):
    """Child-process entry point: run one symbulator_ui function and
    send its result dict back down the pipe."""
    import symbulator_ui
    try:
        conn.send(getattr(symbulator_ui, fn_name)(*args))
    except Exception as exc:  # noqa: BLE001
        conn.send({"ok": False, "error": symbulator_ui._exc_text(exc)})
    finally:
        conn.close()


def _run_in_process(fn_name, args):
    """Run one symbulator_ui function in a killable child process.
    Returns (ok, payload) where payload is the result dict's contents,
    or an error string. Symbolic solving can run away on pathological
    input, and only a separate process can be reliably stopped."""
    parent_conn, child_conn = mp.Pipe(duplex=False)
    proc = mp.Process(target=_call_worker, args=(child_conn, fn_name, args))
    proc.start()
    child_conn.close()  # only the child writes to this end

    if parent_conn.poll(SOLVE_TIMEOUT_S):
        result = parent_conn.recv()
        proc.join(1)
    else:
        proc.terminate()
        proc.join(1)
        return False, (f"The solver took longer than {SOLVE_TIMEOUT_S:g} "
                       "seconds and was stopped. Try a simpler circuit, or "
                       "fewer requested variables for TR analysis.")
    if proc.is_alive():
        proc.kill()

    if not result.get("ok"):
        return False, result.get("error", "Unknown error.")
    return True, {k: v for k, v in result.items() if k != "ok"}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """Serve the single-page app shell -- everything else (solving,
    examples, upload/export) happens over the /api/* routes below via
    JavaScript, so this route just returns the static page once."""
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    """Trivial liveness check for the hosting platform (Render, etc.) to
    poll -- confirms the process is up and answering HTTP, nothing more."""
    return {"ok": True}


def _decode(data: bytes) -> str:
    """Best-effort text decode of an uploaded file, tolerating a BOM and
    Windows-1252 text saved by Notepad."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@app.get("/api/examples")
def api_examples():
    """The built-in examples, re-read from examples.sym on every call so
    the file can be edited without restarting the server."""
    try:
        with open(EXAMPLES_PATH, "rb") as fh:
            text = _decode(fh.read())
    except FileNotFoundError:
        return jsonify({"ok": True, "circuits": [], "warnings": []})
    except OSError as exc:
        return jsonify({"ok": True, "circuits": [],
                        "warnings": [f"Could not read examples file: {exc}"]})
    circuits, warnings = parse_book(text)
    return jsonify({"ok": True, "circuits": circuits, "warnings": warnings})


@app.post("/api/upload")
def api_upload():
    """Parse an uploaded circuit-book file. Nothing is stored on the
    server -- the circuits go straight back to the browser, which holds
    them for the session only."""
    fh = request.files.get("file")
    if fh is None:
        return jsonify({"ok": False, "error": "No file was uploaded."}), 400
    data = fh.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"ok": False,
                        "error": f"File is too large (limit "
                                 f"{MAX_UPLOAD_BYTES // 1024} KB)."}), 400
    if not data.strip():
        return jsonify({"ok": False, "error": "That file is empty."}), 400

    circuits, warnings = parse_book(_decode(data))
    if not circuits:
        return jsonify({"ok": False,
                        "error": "No circuits found in that file. Each circuit "
                                 "needs a [Name] heading above its element lines.",
                        "warnings": warnings}), 400
    name = os.path.basename(fh.filename or "uploaded file")[:80]
    return jsonify({"ok": True, "filename": name,
                    "circuits": circuits, "warnings": warnings})


@app.post("/api/export")
def api_export():
    """Render the browser's live file of circuits as circuit-book text,
    so the user can download it and open it again later (or keep
    building it up). Nothing is stored on the server -- the list of
    circuits comes in whole with every call."""
    from circuitbook import format_book, MAX_CIRCUITS, MAX_NAME_LEN

    data = request.get_json(silent=True) or {}
    raw_circuits = data.get("circuits")
    if not isinstance(raw_circuits, list) or not raw_circuits:
        return jsonify({"ok": False, "error": "Nothing to save yet."}), 400

    circuits = []
    for raw in raw_circuits[:MAX_CIRCUITS]:
        if not isinstance(raw, dict):
            continue
        circuit = {"name": str(raw.get("name") or "Circuit")[:MAX_NAME_LEN],
                   "desc": str(raw.get("desc") or "")[:MAX_DESC_LEN]}
        for field in ("domain", "omega", "vars", "tool", "n1", "n2", "kind",
                      "unknowns", "plotkey", "plotmin", "plotmax", "plotpoints"):
            val = raw.get(field)
            if val:
                circuit[field] = str(val)[:MAX_EXTRA_LEN]
        for field in ("equations", "conditions"):
            items = raw.get(field)
            if isinstance(items, list):
                items = [str(x).strip()[:MAX_EXTRA_LEN] for x in items if str(x).strip()]
                if items:
                    circuit[field] = items[:MAX_EXTRA]
        if circuit["desc"].strip():
            circuits.append(circuit)

    if not circuits:
        return jsonify({"ok": False, "error": "Nothing to save yet."}), 400
    return jsonify({"ok": True, "text": format_book(circuits)})



_MAX_SOLVE_EQS = 10


@app.post("/api/solveq")
def api_solveq():
    """Solve user-supplied equations against the circuit's answers."""
    data = request.get_json(silent=True) or {}
    raw_eqs = data.get("equations") or ""
    if isinstance(raw_eqs, list):
        equations = [str(x).strip() for x in raw_eqs if str(x).strip()]
    else:
        equations = [ln.strip() for ln in re.split(r"[\r\n]+", str(raw_eqs))
                     if ln.strip()]
    unknowns = [u.strip() for u in
                re.split(r"[,\s]+", str(data.get("unknowns") or "")) if u.strip()]
    values = data.get("values") or {}

    raw_conds = data.get("conditions") or ""
    if isinstance(raw_conds, list):
        conditions = [str(x).strip() for x in raw_conds if str(x).strip()]
    else:
        conditions = [ln.strip() for ln in re.split(r"[\r\n]+", str(raw_conds))
                      if ln.strip()]
    conditions = _expand_and(conditions)

    if not equations:
        return jsonify({"ok": False,
                        "error": "Enter at least one equation to solve."}), 400
    if len(equations) > _MAX_SOLVE_EQS:
        return jsonify({"ok": False,
                        "error": f"Too many equations (max {_MAX_SOLVE_EQS})."}), 400
    for eq in equations:
        if len(eq) > MAX_EXTRA_LEN or not _ALLOWED_EQ.match(eq) or "__" in eq:
            return jsonify({"ok": False,
                            "error": f"Equation contains invalid characters: {eq!r}"}), 400
    if len(conditions) > _MAX_SOLVE_EQS:
        return jsonify({"ok": False,
                        "error": f"Too many conditions (max {_MAX_SOLVE_EQS})."}), 400
    for c in conditions:
        if len(c) > MAX_EXTRA_LEN or not _ALLOWED_COND.match(c) or "__" in c:
            return jsonify({"ok": False,
                            "error": f"Condition contains invalid characters: {c!r}"}), 400
    if len(unknowns) > MAX_EXTRA:
        return jsonify({"ok": False, "error": "Too many unknowns."}), 400
    for u in unknowns:
        if not _VARNAME.match(u):
            return jsonify({"ok": False, "error": f"Invalid unknown name: {u!r}"}), 400
    if not isinstance(values, dict) or len(values) > 300:
        return jsonify({"ok": False, "error": "Invalid values payload."}), 400

    clean = {}
    for k, v in values.items():
        if (isinstance(k, str) and _VARNAME.match(k) and isinstance(v, str)
                and len(v) <= 4000 and _ALLOWED.match(v) and "__" not in v):
            clean[k] = v

    digits = _clean_digits(data.get("digits"))
    si = bool(data.get("si"))
    approx = bool(data.get("approx"))
    units = bool(data.get("units"))
    real_only = bool(data.get("real_only"))

    t0 = time.time()
    ok, payload = _run_in_process(
        "solveq_ui",
        (equations, unknowns, clean, digits, si, approx, units, real_only,
         conditions))
    elapsed = round(time.time() - t0, 2)
    if not ok:
        return jsonify({"ok": False, "error": payload, "elapsed": elapsed}), 422
    return jsonify({"ok": True, "elapsed": elapsed, **payload})


@app.errorhandler(413)
def too_large(_exc):
    """Flask calls this automatically when a request body exceeds
    MAX_CONTENT_LENGTH, before the route handler even runs -- catches an
    oversized upload that slips past api_upload's own length check
    because Flask rejects it at the WSGI layer first."""
    return jsonify({"ok": False,
                    "error": f"File is too large (limit "
                             f"{MAX_UPLOAD_BYTES // 1024} KB)."}), 413


_VALID_TOOLS = {"solve", "th", "er", "port"}
_NODE_RE = re.compile(r"^[A-Za-z0-9_]{1,20}$")


@app.post("/api/solve")
def api_solve():
    """Main solve endpoint: validate the posted circuit and options,
    resolve any ambiguous bare-suffix values (asking the browser back for
    a decision if needed -- see the "Ambiguity check" block below), then
    hand off to solve_ui/th/er/port (via symbulator_ui, in the killable
    child process) and return its formatted answers. Handles both a
    normal circuit solve and the th/er/port two-terminal tools, selected
    by `tool` in the posted JSON."""
    data = request.get_json(silent=True) or {}
    desc = str(data.get("desc", "")).strip()
    # Elements may be separated by ":" (calculator style) or by new
    # lines (natural in the textarea) -- normalize before validating.
    desc = re.sub(r"[\r\n]+", ":", desc)
    desc = re.sub(r":{2,}", ":", desc).strip(":")
    domain = str(data.get("domain", "")).strip().lower()
    omega = str(data.get("omega", "")).strip()
    variables = data.get("variables") or None
    if isinstance(variables, str):
        variables = [v.strip() for v in variables.split(",") if v.strip()]
    tool = str(data.get("tool", "solve")).strip().lower() or "solve"
    n1 = str(data.get("n1", "")).strip()
    n2 = str(data.get("n2", "")).strip()
    kind = str(data.get("kind", "z")).strip().lower()
    digits = _clean_digits(data.get("digits"))
    si = bool(data.get("si"))
    units = bool(data.get("units"))
    use_rms = bool(data.get("use_rms"))
    approx = bool(data.get("approx"))

    def _lines(field):
        """Read `field` from the posted JSON as a list of non-blank
        strings, whether the browser sent it as an actual JSON array or
        as one newline/carriage-return-separated block of text (which is
        what a plain <textarea> gives you) -- so the expert-mode
        equations/conditions boxes work the same either way."""
        raw = data.get(field) or ""
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        return [ln.strip() for ln in re.split(r"[\r\n]+", str(raw)) if ln.strip()]

    extra_equations = _lines("equations")
    extra_conditions = _expand_and(_lines("conditions"))
    extra_unknowns = [u.strip() for u in
                      re.split(r"[,\s]+", str(data.get("unknowns") or ""))
                      if u.strip()]

    err = _validate(desc, domain, omega, variables)
    if not err:
        err = _validate_extras(extra_equations, extra_unknowns, extra_conditions)
    if not err and tool != "solve" and (extra_equations or extra_unknowns
                                        or extra_conditions):
        err = "Added equations/unknowns/conditions only apply to Solve circuit."
    if not err and tool not in _VALID_TOOLS:
        err = "Unknown tool."
    if not err and tool != "solve":
        if domain not in ("dc", "ac"):
            err = "Thevenin / impedance / two-port tools work in DC or AC only."
        elif not (_NODE_RE.match(n1) and _NODE_RE.match(n2)):
            err = "Give the two port nodes (n1 and n2) for this tool."
        elif tool == "port" and kind not in ("z", "y", "h", "g", "a", "b"):
            err = "Two-port kind must be one of z, y, h, g, a, b."
    if err:
        return jsonify({"ok": False, "error": err}), 400

    # ---- Ambiguity check: a bare value like "1k" could be the SI unit
    # (1'k = 1000) or number*variable (1*k). If any are present and the
    # user hasn't said which, send the question back instead of solving;
    # once choices arrive, rewrite the description to the explicit form.
    choices = data.get("suffix_choices") or {}
    if not isinstance(choices, dict):
        choices = {}
    choices = {str(k): str(v) for k, v in choices.items()
               if isinstance(k, str) and len(k) <= 30 and v in ("si", "var")}

    desc_used = None
    imaginary_notes = []
    normalised, imaginary_notes = normalise_imaginary(desc)
    if normalised != desc:
        desc = normalised
    try:
        from symbulator.elements import (parse_circuit, ambiguous_in_elements,
                                         _VALUE_FIELD_IDX)
        from symbulator.si_prefix import bare_suffix_match, _BARE_SUFFIX_EXP
        elements = parse_circuit(desc)
        ambiguous = ambiguous_in_elements(elements)
    except Exception as exc:  # parse errors get the same friendly text
        return jsonify({"ok": False, "error": str(exc)[:400]}), 422

    if ambiguous:
        unresolved = [a for a in ambiguous if a["token"] not in choices]
        if unresolved:
            groups = {}
            for a in ambiguous:
                g = groups.setdefault(a["token"], {
                    "token": a["token"], "number": a["number"],
                    "letter": a["letter"],
                    "exponent": _BARE_SUFFIX_EXP[a["letter"]],
                    "elements": []})
                g["elements"].append(a["element"])
            return jsonify({"ok": False, "ambiguous": list(groups.values())})
        # Every token has an answer: rewrite each ambiguous value field
        # to the explicit spelling the user chose.
        for e in elements:
            for idx in _VALUE_FIELD_IDX.get(e.kind, ()):
                if idx >= len(e.fields):
                    continue
                m = bare_suffix_match(e.fields[idx])
                if m:
                    tok = e.fields[idx].strip()
                    sep = "'" if choices[tok] == "si" else "*"
                    e.fields[idx] = f"{m[0]}{sep}{m[1]}"

    # Always echo the circuit back one element per line, regardless of
    # whether anything above needed fixing up -- easier to read/edit
    # than a single ':'-joined line, and consistent every time you run,
    # not just on the two occasions (imaginary-unit normalizing, an
    # ambiguous suffix being resolved) that used to trigger it.
    desc = ":".join(e.name + "," + ",".join(e.fields) for e in elements)
    desc_used = desc.replace(":", "\n")

    t0 = time.time()
    ok, payload = _run_in_process(
        "solve_ui", (desc, domain, omega, variables, tool, n1, n2, kind,
                        extra_equations, extra_unknowns, extra_conditions,
                        digits, si, units, use_rms, approx))
    elapsed = round(time.time() - t0, 2)

    if not ok:
        # The notes matter most when the solve failed: "normalised '5*i'
        # to '5j'" is often the explanation for the error underneath it.
        return jsonify({"ok": False, "error": payload, "elapsed": elapsed,
                        "notes": imaginary_notes}), 422

    payload.setdefault("notes", [])
    payload["notes"] = imaginary_notes + list(payload["notes"])
    return jsonify({"ok": True, "domain": domain, "tool": tool,
                    "elapsed": elapsed, "desc_used": desc_used,
                    "digits": digits, "si": si, "units": units,
                    "use_rms": use_rms, "approx": approx,
                    "nodes": payload["nodes"],
                    "elements": payload["elements"], "extras": payload["extras"],
                    "values": payload["values"],
                    "equations": payload["equations"],
                    "notes": payload["notes"]})


_VALID_PLOT_TOOLS = {"time", "bode"}
_MAX_RANGE = 1e15  # generous ceiling; keeps a typo from hanging np.logspace/linspace


def _clean_range(raw, lo_default, hi_default):
    """Parse a plot range's min/max into floats, falling back to the
    given defaults for blank input. Returns (lo, hi, error)."""
    try:
        lo = float(raw.get("min")) if raw.get("min") not in (None, "") else lo_default
        hi = float(raw.get("max")) if raw.get("max") not in (None, "") else hi_default
    except (TypeError, ValueError):
        return None, None, "Range values must be numbers."
    if not (-_MAX_RANGE < lo < _MAX_RANGE and -_MAX_RANGE < hi < _MAX_RANGE):
        return None, None, "Range values are out of bounds."
    return lo, hi, None


@app.post("/api/plot")
def api_plot():
    """Plot endpoint for the two sampling-based tools: "Plot vs time"
    (tr()'s response over a time range) and "Bode plot" (fd()'s
    magnitude/phase over a frequency sweep). Separate from /api/solve
    because the shape of both the request (a range + point count instead
    of a domain) and the response (number arrays for a chart instead of
    formatted equations) are different enough that folding them into the
    same endpoint would complicate both."""
    data = request.get_json(silent=True) or {}
    desc = str(data.get("desc", "")).strip()
    desc = re.sub(r"[\r\n]+", ":", desc)
    desc = re.sub(r":{2,}", ":", desc).strip(":")
    tool = str(data.get("tool", "")).strip().lower()
    key = str(data.get("key", "")).strip()
    try:
        n = int(data.get("n", 200))
    except (TypeError, ValueError):
        n = -1

    def _lines(field):
        raw = data.get(field) or ""
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        return [ln.strip() for ln in re.split(r"[\r\n]+", str(raw)) if ln.strip()]

    extra_equations = _lines("equations")
    extra_conditions = _expand_and(_lines("conditions"))
    extra_unknowns = [u.strip() for u in
                      re.split(r"[,\s]+", str(data.get("unknowns") or ""))
                      if u.strip()]

    err = None
    if not desc:
        err = "Please enter a circuit description."
    elif len(desc) > MAX_DESC_LEN:
        err = f"Circuit description too long (max {MAX_DESC_LEN} characters)."
    elif not _ALLOWED.match(desc) or "__" in desc:
        err = "Circuit description contains characters that aren't used in Symbulator syntax."
    elif tool not in _VALID_PLOT_TOOLS:
        err = "Unknown plot tool."
    elif not key or not _VARNAME.match(key):
        err = "Give a variable to plot, e.g. v_2 or i_r1."
    elif not (2 <= n <= MAX_PLOT_POINTS):
        err = f"Number of points must be between 2 and {MAX_PLOT_POINTS}."
    if not err:
        err = _validate_extras(extra_equations, extra_unknowns, extra_conditions)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    if tool == "time":
        t_min, t_max, rng_err = _clean_range(data, 0.0, 1.0)
        if rng_err:
            return jsonify({"ok": False, "error": rng_err}), 400
        fn_name, args = "plot_time_ui", (desc, key, t_min, t_max, n,
                                         extra_equations, extra_unknowns, extra_conditions)
    else:
        f_min, f_max, rng_err = _clean_range(data, 1.0, 1000.0)
        if rng_err:
            return jsonify({"ok": False, "error": rng_err}), 400
        if f_min <= 0 or f_max <= 0:
            return jsonify({"ok": False, "error": "Bode frequencies must be positive (Hz)."}), 400
        fn_name, args = "bode_ui", (desc, key, f_min, f_max, n,
                                    extra_equations, extra_unknowns, extra_conditions)

    t0 = time.time()
    ok, payload = _run_in_process(fn_name, args)
    elapsed = round(time.time() - t0, 2)
    if not ok:
        return jsonify({"ok": False, "error": payload, "elapsed": elapsed}), 422
    return jsonify({"ok": True, "tool": tool, "elapsed": elapsed, **payload})


_EXPR_MAX = 500


@app.post("/api/evaluate")
def api_evaluate():
    """Evaluate a standalone expression (the "Evaluate" card): substitute
    the posted name->value pairs into `expr` and format the result the
    same way a solved circuit answer would be -- lets the user plug
    solved values into a follow-up formula (e.g. power = v * i) without
    re-solving the whole circuit."""
    data = request.get_json(silent=True) or {}
    expr = str(data.get("expr", "")).strip()
    values = data.get("values") or {}

    if not expr:
        return jsonify({"ok": False, "error": "Enter an expression to evaluate."}), 400
    if len(expr) > _EXPR_MAX or not _ALLOWED.match(expr) or "__" in expr:
        return jsonify({"ok": False, "error": "Expression contains invalid characters."}), 400
    if not isinstance(values, dict) or len(values) > 300:
        return jsonify({"ok": False, "error": "Invalid values payload."}), 400
    clean = {}
    for k, v in values.items():
        if (isinstance(k, str) and _VARNAME.match(k) and isinstance(v, str)
                and len(v) <= 4000 and _ALLOWED.match(v) and "__" not in v):
            clean[k] = v

    digits = _clean_digits(data.get("digits"))
    si = bool(data.get("si"))
    approx = bool(data.get("approx"))
    t0 = time.time()
    ok, payload = _run_in_process("evaluate_ui", (expr, clean, digits, si, approx))
    elapsed = round(time.time() - t0, 2)
    if not ok:
        return jsonify({"ok": False, "error": payload, "elapsed": elapsed}), 422
    return jsonify({"ok": True, "elapsed": elapsed, **payload})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
