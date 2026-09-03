# -*- coding: utf-8 -*-
"""Prove that an entry survives the trip from the form to a file and back.

#250 (3 Sep 2026). An entry is written by the front end's inputsSnapshot(),
handed to one of two export paths (app.py's /api/export on the server, the
offline bridge's export_book), rendered by circuitbook.format_book, and
read back by circuitbook.parse_book. Each of those had its own idea of
which fields exist, and the ideas had drifted: the server export dropped
`defines` and `evaluate_conditions`, the offline one dropped `plotx` and
`defines`, and neither carried `polar` or `show_equations`. Nothing showed
inside a session, because the entries live in the browser -- the values
went missing only in a downloaded file.

There is one field list now (circuitbook.SCALAR_FIELDS / BOOL_FIELDS /
LIST_FIELDS, derived from the parser's own tables) and one sanitiser
(circuitbook.clean_circuits) behind both exports. This script proves it
from three directions:

1. **The round trip.** A circuit with every field set is written, parsed,
   cleaned and written again. Every field must come back with its value,
   and the second file must equal the first byte for byte. A writer that
   never writes a field, a parser that cannot read one, or a sanitiser
   that drops one all fail here.
2. **The front end.** Every key inputsSnapshot() returns must be a field
   the file format knows. A key added to the form and forgotten in
   circuitbook would be saved in the browser and lost on download.
3. **Both exports call the shared sanitiser.** A hand-kept copy creeping
   back into either would reopen the original fault.

Run from anywhere; exits 1 with a message on the first failure. Wired into
build_local.py, so every offline build runs it. To see it go red, delete
"plotx" from circuitbook._KEYS, or add `bogus: 1` to inputsSnapshot().
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent
sys.path.insert(0, str(SERVER))

import circuitbook as cb  # noqa: E402


def fail(msg: str) -> None:
    print("check_export_fields: " + msg)
    sys.exit(1)


# --- 1. the round trip ------------------------------------------------------

def full_circuit() -> dict:
    """One circuit with every field the format knows set to a value that
    names the field, so a lost one is identifiable in the failure."""
    c = {"name": "Round trip", "desc": "v,1,0,10\nr,1,2,rx\nr,2,0,1e3"}
    for i, f in enumerate(cb.SCALAR_FIELDS):
        c[f] = f"{f}_value_{i}"
    # rms and polar are written for AC only; show_equations only when on.
    c["domain"] = "ac"
    c["rounding"] = "5"
    c["plotpoints"] = "50"
    c["image"] = "https://example.org/pic.png [200px]"
    for f in cb.BOOL_FIELDS:
        c[f] = True
    for f in cb.LIST_FIELDS:
        c[f] = [f"{f} one", f"{f} two"]
    return c


def check_round_trip() -> int:
    full = full_circuit()
    text1 = cb.format_book([full], "Round trip book")
    parsed, warnings, title = cb.parse_book(text1)
    if warnings:
        fail("parse_book warned on the writer's own output:\n  "
             + "\n  ".join(warnings))
    if len(parsed) != 1:
        fail(f"expected one circuit back, got {len(parsed)}")
    if title != "Round trip book":
        fail(f"the file's title came back as {title!r}")
    back = parsed[0]
    lost = [f for f in full if f not in back]
    if lost:
        fail("written but not read back (the writer skipped it, or the "
             "parser does not know it): " + ", ".join(lost))
    wrong = [f for f in full if back[f] != full[f]]
    if wrong:
        fail("read back with a different value: "
             + ", ".join(f"{f}={back[f]!r} (wrote {full[f]!r})" for f in wrong))

    cleaned = cb.clean_circuits(parsed)
    if len(cleaned) != 1:
        fail("clean_circuits dropped the circuit")
    dropped = [f for f in back if f not in cleaned[0]]
    if dropped:
        fail("clean_circuits dropped: " + ", ".join(dropped))
    changed = [f for f in back if cleaned[0][f] != back[f]]
    if changed:
        fail("clean_circuits changed: "
             + ", ".join(f"{f}={cleaned[0][f]!r}" for f in changed))

    text2 = cb.format_book(cleaned, title)
    if text2 != text1:
        fail("the file is not stable across a round trip:\n--- first\n"
             + text1 + "\n--- second\n" + text2)

    # The booleans the other way: every one off must come back off, and
    # only `units` may default to on when a file says nothing about it.
    off = {"name": "Off", "desc": "r,1,0,1", "domain": "ac"}
    for f in cb.BOOL_FIELDS:
        off[f] = False
    back_off = cb.parse_book(cb.format_book(cb.clean_circuits([off])))[0][0]
    # show_equations and solve_real_only are written only when on, so a
    # file with them off simply has no line; the parser leaves them absent
    # and the front end reads absence as off. The always-written ones must
    # be present and False.
    for f in ("si", "units", "rms", "polar"):
        if back_off.get(f) is not False:
            fail(f"{f}: False did not survive the round trip (got {back_off.get(f)!r})")
    silent = cb.clean_circuits([{"name": "Silent", "desc": "r,1,0,1"}])[0]
    if silent["units"] is not True:
        fail("an entry that says nothing about units must mean 'show units'")
    for f in cb.BOOL_FIELDS:
        if f != "units" and silent[f] is not False:
            fail(f"an entry that says nothing about {f} must mean off")
    return len(full) - 2


# --- 2. the front end -------------------------------------------------------

def check_snapshot_keys() -> int:
    template = SERVER / "templates" / "index.html"
    text = template.read_text(encoding="utf-8")
    m = re.search(r"function inputsSnapshot\(\) \{(.*?)\r?\n\}", text, re.S)
    if not m:
        fail(f"could not find inputsSnapshot() in {template}")
    body = m.group(1)
    # A returned key is a bare identifier at the start of a line, followed
    # by a colon -- `plotkey: hasPlot ? ...`. Comments are stripped first
    # so a prose "note:" cannot be read as one.
    body = re.sub(r"//[^\n]*", "", body)
    keys = re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", body, re.M)
    if not keys:
        fail("inputsSnapshot() returned no keys that this script could read")
    known = set(cb.SCALAR_FIELDS) | set(cb.BOOL_FIELDS) | set(cb.LIST_FIELDS)
    known |= {"desc"}
    unknown = [k for k in keys if k not in known]
    if unknown:
        fail("inputsSnapshot() saves a key the file format cannot write: "
             + ", ".join(unknown)
             + " -- add it to circuitbook._KEYS or _MULTI, or it is lost "
               "on download")
    return len(keys)


# --- 3. both exports use the shared sanitiser -------------------------------

def check_exports_share() -> None:
    server_app = SERVER / "app.py"
    if "clean_circuits(" not in server_app.read_text(encoding="utf-8"):
        fail("app.py's /api/export no longer calls circuitbook.clean_circuits")
    bridge = SERVER.parent / "local" / "bridge.py"
    if not bridge.is_file():
        print("  note: repos/local is not beside this tree, so the offline "
              "bridge's export was not checked.")
        return
    if "clean_circuits(" not in bridge.read_text(encoding="utf-8"):
        fail("the offline bridge's export_book no longer calls "
             "circuitbook.clean_circuits")


def main() -> None:
    n_fields = check_round_trip()
    n_keys = check_snapshot_keys()
    check_exports_share()
    print(f"check_export_fields: ok -- {n_fields} fields round-trip, "
          f"{n_keys} snapshot keys all known, both exports share "
          f"clean_circuits")


if __name__ == "__main__":
    main()
