"""
The "circuit book" format: a plain-text file holding one or more named
circuits, used both for the site's built-in examples (examples.sym) and
for files users upload.

    # comments start with a hash

    [Voltage divider (DC)]
    analysis: dc
    e1,1,0,5
    r1,1,2,1'k
    r2,2,0,1'k

    [Thevenin equivalent]
    tool: th
    n1: 2
    n2: 0
    e1,1,0,12
    r1,1,2,4'k
    r2,2,0,2'k

A `[Name]` line starts a new circuit and supplies its dropdown label.
`key: value` lines carry the analysis setup; anything else is a circuit
line, written exactly as it would be typed into the textarea. A circuit
ends where the next `[Name]` begins.

Only *known* keys are treated as metadata, which is what lets a circuit
line like "e1,1,0,5:r1,1,2,1'k" (colon-separated elements, the
calculator's own style) pass through untouched -- its "key" would be
"e1,1,0,5", which isn't in the table below.

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
    "plotkey": "plotkey",
    "plotmin": "plotmin",
    "plotmax": "plotmax",
    "plotpoints": "plotpoints",
}
# Keys that may appear several times and accumulate into a list.
_MULTI = {"equations": "equations", "equation": "equations",
          "conditions": "conditions", "condition": "conditions"}

_SECTION_RE = re.compile(r"^\[(?P<name>.+)\]\s*$")
_KEY_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*:\s*(?P<val>.*)$")

MAX_CIRCUITS = 200
MAX_NAME_LEN = 80


def parse_book(text: str) -> Tuple[List[dict], List[str]]:
    """Parse circuit-book text. Returns (circuits, warnings). Each
    circuit is a dict with "name", "desc" (newline-joined circuit
    lines) and whatever metadata fields were given."""
    circuits: List[dict] = []
    warnings: List[str] = []
    current: dict | None = None
    lines: List[str] = []

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
                current[_KEYS[key]] = val
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
    return circuits, warnings


def format_book(circuits: List[dict]) -> str:
    """Render circuits back out as circuit-book text -- the inverse of
    parse_book, so a session can be saved and re-loaded."""
    out: List[str] = ["# Symbulator circuit book", ""]
    for c in circuits:
        out.append(f"[{c.get('name', 'Circuit')}]")
        for key, field in (("analysis", "domain"), ("omega", "omega"),
                           ("variables", "vars"), ("tool", "tool"),
                           ("n1", "n1"), ("n2", "n2"), ("kind", "kind"),
                           ("unknowns", "unknowns"), ("note", "note"),
                           ("plotkey", "plotkey"), ("plotmin", "plotmin"),
                           ("plotmax", "plotmax"), ("plotpoints", "plotpoints")):
            val = c.get(field)
            if val:
                out.append(f"{key}: {val}")
        for key, field in (("equation", "equations"), ("condition", "conditions")):
            for val in c.get(field, []) or []:
                out.append(f"{key}: {val}")
        out.append(c.get("desc", "").strip())
        out.append("")
    return "\n".join(out)
