"""
The "circuit book" format: a plain-text file holding one or more named
circuits, used both for the site's built-in examples (the .cir files
in examples/) and for files users upload.

    [Voltage divider (DC)]

    e1,1,0,5
    r1,1,2,1'k
    r2,2,0,1'k

    analysis: dc
    rounding: exact
    si: no
    units: yes


    [Thevenin equivalent]

    e1,1,0,12
    r1,1,2,4'k
    r2,2,0,2'k

    tool: th
    n1: 2
    n2: 0
    analysis: dc
    rounding: exact
    si: no
    units: yes

A `[Name]` line starts a new circuit and supplies its dropdown label,
followed by its circuit lines, written exactly as they'd be typed into
the textarea. `key: value` lines carry everything else, in one
unbroken block -- analysis type and (if the circuit uses it) Expert
Mode, then Settings (rms only for AC, where it means anything), then
(if present) Evaluate / Solve-equations / Plot -- which is the order
"Save this circuit to the input file" writes them in, though nothing
about *parsing* cares about order: a `key: value` line is metadata and
anything else is a circuit line, wherever in the section it appears. A
circuit ends where the next `[Name]` begins.

Only *known* keys are treated as metadata, which is what lets a circuit
line like "e1,1,0,5:r1,1,2,1'k" (colon-separated elements, the
calculator's own style) pass through untouched -- its "key" would be
"e1,1,0,5", which isn't in the table below. Every key is optional when
hand-writing a file: parsing falls back to the app's own defaults
(rounding exact, SI prefixes and RMS off, units on) for whichever ones
are left out, exactly as if Settings had never been touched.

Parsing never raises on bad content: unknown keys and stray lines before
the first [Name] are collected as warnings so the caller can show them
without losing the circuits that did parse.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Metadata key -> the JSON field the front end uses. Aliases let the
# file read naturally ("analysis:" or "domain:", "vars:" or
# "variables:") without the front end caring which was written.
_KEYS = {
    "analysis": "domain",
    "domain": "domain",
    "omega": "omega",
    "w": "omega",
    "variables": "vars",
    "vars": "vars",
    "tool": "tool",
    "n1": "n1",
    "n2": "n2",
    "kind": "kind",
    "unknowns": "unknowns",
    "note": "note",
    # The Plot card is a separate tool from the Analysis one above, so it
    # gets its own key. Older files stored the plot type in "tool:" -- see
    # applyCircuit() in the front end, which still reads that form.
    "plottool": "plottool",
    "plotkey": "plotkey",
    "plotmin": "plotmin",
    "plotmax": "plotmax",
    "plotpoints": "plotpoints",
    # Settings -- captured whenever a circuit is saved from the app (not
    # just "if applicable" like Expert Mode/Evaluate/Solve/Plot, since
    # Settings always has *some* value). Booleans are written "yes"/"no"
    # so the file stays readable by hand; see _BOOL_FIELDS below for how
    # they come back out of parse_book as real True/False.
    "rounding": "rounding",
    "si": "si",
    "units": "units",
    "rms": "rms",
    # Show AC answers as polar phasors. The front end has always saved and
    # restored this, but it was missing here, so it was dropped on the way
    # into the file and every reload came back rectangular.
    "polar": "polar",
    # The Evaluate box, and the standalone "Solve equations" tool -- both
    # separate from a circuit's own Expert Mode (equation/condition/
    # unknowns above), which is why they get their own key names instead
    # of colliding with those. Evaluate's Conditions box is one of the
    # repeatable keys, in _MULTI below, since it holds one per line.
    "evaluate": "evaluate",
    "solve_unknowns": "solve_unknowns",
    "solve_real_only": "solve_real_only",
}
# Keys that may appear several times and accumulate into a list. Plural,
# because the field holds several -- the same rule as unknowns and
# variables. The singular spellings these once had are not accepted: a
# file still using them fails loudly, since an unknown key is reported
# and kept as a circuit line rather than quietly dropped.
_MULTI = {"equations": "equations",
          "conditions": "conditions",
          # The Define field: `name = expression` shorthands, expanded
          # into every input before anything is parsed. Repeatable, one
          # definition per line, so plural like the rest of this group.
          "defines": "defines",
          # Evaluate's own Conditions box (#96). Named for its card, like
          # `solve_conditions` is, so it cannot collide with a circuit's
          # Expert Mode `conditions` above -- three different boxes, three
          # keys, and a file that says which is which.
          "evaluate_conditions": "evaluate_conditions",
          "solve_equations": "solve_equations",
          "solve_conditions": "solve_conditions"}

# JSON fields (the _KEYS values above, not the file-text keys) that are
# booleans rather than plain text -- parse_book converts their text
# ("yes"/"no"/...) to real True/False so the front end never has to.
_BOOL_FIELDS = {"si", "units", "rms", "polar", "solve_real_only"}
_TRUE_WORDS = {"yes", "true", "1", "on"}

_SECTION_RE = re.compile(r"^\[(?P<name>.+)\]\s*$")
_KEY_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*:\s*(?P<val>.*)$")

MAX_CIRCUITS = 200
MAX_NAME_LEN = 80
MAX_TITLE_LEN = 120


def _truthy(val: str) -> bool:
    """Read a hand-typeable "yes"/"no"-style value as a bool."""
    return val.strip().lower() in _TRUE_WORDS


def parse_book(text: str) -> Tuple[List[dict], List[str], str]:
    """Parse circuit-book text. Returns (circuits, warnings, title). Each
    circuit is a dict with "name", "desc" (newline-joined circuit
    lines) and whatever metadata fields were given.

    `title` is the file's own name for itself, from a `title:` line above
    the first entry, and is "" when the file does not give one."""
    circuits: List[dict] = []
    warnings: List[str] = []
    current: dict | None = None
    lines: List[str] = []
    title = ""

    def flush():
        """Close out the circuit being accumulated in `current`/`lines`
        (called when a new [Name] section starts, and once more at the
        end of the file): join its collected lines into one `desc`
        string and append it to `circuits`, or -- if it never got any
        circuit lines -- drop it with a warning instead of adding an
        empty circuit."""
        nonlocal current, lines
        if current is not None:
            desc = "\n".join(lines).strip()
            if desc:
                current["desc"] = desc
                circuits.append(current)
            else:
                warnings.append(f"'{current['name']}' has no circuit lines; skipped.")
        current, lines = None, []

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = _SECTION_RE.match(line)
        if m:
            flush()
            if len(circuits) >= MAX_CIRCUITS:
                warnings.append(
                    f"Stopped after {MAX_CIRCUITS} circuits; the rest of the "
                    f"file was ignored.")
                break
            name = m.group("name").strip()[:MAX_NAME_LEN] or f"Circuit {len(circuits) + 1}"
            current = {"name": name}
            lines = []
            continue

        if current is None:
            # A `title:` above the first [Name] is the file's own title --
            # what the interface shows in place of the filename. Anything
            # else up here is still a stray.
            km = _KEY_RE.match(line)
            if km and km.group("key").lower() == "title":
                title = km.group("val").strip()[:MAX_TITLE_LEN]
                continue
            warnings.append(f"Line {lineno} appears before the first [Name] heading; ignored.")
            continue

        km = _KEY_RE.match(line)
        if km:
            key = km.group("key").lower()
            val = km.group("val").strip()
            if key in _MULTI:
                current.setdefault(_MULTI[key], []).append(val)
                continue
            if key in _KEYS:
                field = _KEYS[key]
                current[field] = _truthy(val) if field in _BOOL_FIELDS else val
                continue
            # An unknown key: could be a typo, or could be a circuit
            # line we shouldn't swallow. Keep it as a circuit line and
            # mention it, so nothing silently disappears.
            warnings.append(
                f"Line {lineno}: '{key}' isn't a known setting; treated as a circuit line.")

        lines.append(line)

    flush()
    if not circuits and not warnings:
        warnings.append("No circuits found. Each circuit needs a [Name] heading.")
    return circuits, warnings, title


def _bool_word(val) -> str:
    return "yes" if val else "no"


def format_book(circuits: List[dict], title: str = "") -> str:
    """Render circuits back out as circuit-book text -- the inverse of
    parse_book, so a session can be saved and re-loaded. Each circuit is
    written in the same order "Save this circuit to the input file"
    builds it in: circuit description first, then analysis type and
    (if applicable) Expert Mode, then Settings, then Evaluate /
    Solve-equations / Plot, if any of those were in use."""
    out: List[str] = ["# Symbulator circuit book", ""]
    # The file's own title, above every entry, so a file that was given one
    # keeps it when it is saved and downloaded again.
    if title.strip():
        out.extend([f"title: {title.strip()[:MAX_TITLE_LEN]}", ""])
    for index, c in enumerate(circuits):
        # Two blank lines before every circuit but the first, so each block
        # stands clearly apart when the file is read or edited by hand.
        if index:
            out.extend(["", ""])
        out.append(f"[{c.get('name', 'Circuit')}]")
        # One blank under the name, so it reads as a heading rather than
        # the first line of the netlist below it.
        out.append("")

        # 1. Circuit description.
        out.append(c.get("desc", "").strip())

        # 2. The Define field, then analysis type, then (if applicable)
        # Expert Mode. Definitions come first because they are read before
        # anything else is: they belong directly under the netlist they
        # rewrite, not among the settings.
        analysis: List[str] = []
        for val in c.get("defines", []) or []:
            analysis.append(f"defines: {val}")
        for key, field in (("analysis", "domain"), ("omega", "omega"),
                           ("variables", "vars"), ("tool", "tool"),
                           ("n1", "n1"), ("n2", "n2"), ("kind", "kind"),
                           ("note", "note")):
            val = c.get(field)
            if val:
                analysis.append(f"{key}: {val}")
        val = c.get("unknowns")
        if val:
            analysis.append(f"unknowns: {val}")
        for key, field in (("equations", "equations"), ("conditions", "conditions")):
            for val in c.get(field, []) or []:
                analysis.append(f"{key}: {val}")
        meta: List[str] = list(analysis)

        # 3. Settings -- always written (not "if applicable"): a saved
        # circuit always has *some* rounding/display state, even if it's
        # every default. Falls back to the app's own defaults so a
        # circuit dict that never touched Settings (e.g. one parsed
        # straight out of an older file) still renders something correct.
        meta.append(f"rounding: {c.get('rounding') or 'exact'}")
        meta.append(f"si: {_bool_word(c.get('si'))}")
        meta.append(f"units: {_bool_word(c.get('units', True))}")
        # The RMS convention applies to AC power only, so writing it for a
        # DC or transient circuit records a setting that cannot do anything
        # there. Left out entirely unless the analysis is AC.
        if (c.get("domain") or "dc").strip().lower() == "ac":
            meta.append(f"rms: {_bool_word(c.get('rms'))}")
            # Polar form is an AC-only display too: outside AC every answer
            # is real or a function of s or t, and the checkbox greys out.
            meta.append(f"polar: {_bool_word(c.get('polar'))}")

        # 4. Evaluate / Solve-equations / Plot, if any were in use.
        extra: List[str] = []
        if c.get("evaluate"):
            extra.append(f"evaluate: {c['evaluate']}")
        for val in c.get("evaluate_conditions", []) or []:
            extra.append(f"evaluate_conditions: {val}")
        for val in c.get("solve_equations", []) or []:
            extra.append(f"solve_equations: {val}")
        val = c.get("solve_unknowns")
        if val:
            extra.append(f"solve_unknowns: {val}")
        for val in c.get("solve_conditions", []) or []:
            extra.append(f"solve_conditions: {val}")
        if c.get("solve_real_only"):
            extra.append("solve_real_only: yes")
        for key, field in (("plottool", "plottool"), ("plotkey", "plotkey"),
                           ("plotmin", "plotmin"), ("plotmax", "plotmax"),
                           ("plotpoints", "plotpoints")):
            val = c.get(field)
            if val:
                extra.append(f"{key}: {val}")
        meta.extend(extra)
        # One block, one blank line above it: every tagged line for this
        # circuit reads as a single run of settings rather than three
        # groups the reader has to reassemble.
        if meta:
            out.append("")
            out.extend(meta)

    # One trailing newline for the file, rather than one per circuit --
    # the gaps between circuits are written above instead.
    out.append("")
    return "\n".join(out)
