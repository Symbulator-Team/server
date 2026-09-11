"""Shared entry enumeration for the schematic work.

Every built-in entry of every .cir book, with the description the app
would actually draw -- `ground_references(port_references(...))`, not
the raw `desc` field. Scoring the raw field scores a different circuit
(the handover's warning, and #320's reason for the wrapper).
"""
import os
import sys

# Found from this file rather than hard-coded: schematic_lab -> tools ->
# server -> repos. `review_schematics.py` had one `dirname` too many
# here once and quietly reviewed whatever pip had installed instead of
# the working tree, for months (#212).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
SERVER = os.path.join(ROOT, "server")
SOLVER = os.path.join(ROOT, "solver")
EXAMPLES = os.path.join(SERVER, "examples")

if SOLVER not in sys.path:
    sys.path.insert(0, SOLVER)
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)


def entries():
    """[(book, index, name, desc)] over every .cir in examples/."""
    from circuitbook import parse_book
    from symbulator_ui import port_references, ground_references
    out = []
    for book in sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".cir")):
        with open(os.path.join(EXAMPLES, book), encoding="utf-8") as f:
            circuits, _warn, _title = parse_book(f.read())
        for i, c in enumerate(circuits):
            desc = ground_references(c["desc"], port_references(
                c.get("tool"), c.get("n1"), c.get("n2")))
            out.append((book, i, c["name"], desc))
    return out


def render_all():
    """{(book, index): (name, svg_or_None, error)}"""
    from symbulator.schematic import to_svg
    out = {}
    for book, i, name, desc in entries():
        try:
            out[(book, i)] = (name, to_svg(desc), None)
        except Exception as ex:                      # noqa: BLE001
            out[(book, i)] = (name, None, "%s: %s" % (type(ex).__name__, ex))
    return out


if __name__ == "__main__":
    es = entries()
    books = sorted({b for b, _, _, _ in es})
    print("%d entries across %d books" % (len(es), len(books)))
    for b in books:
        print("  %-22s %d" % (b, sum(1 for x in es if x[0] == b)))
