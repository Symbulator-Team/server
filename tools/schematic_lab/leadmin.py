"""What lead does the book already stand at?

`LEAD_MIN` decides how far the band deflates, and a number chosen to
make one drawing look right is exactly the kind #372 warns about --
`OP_ABOVE_GAP` was fitted to this book and comes out non-monotonic
under a sweep. So read it off the shipped drawings instead: render each
at the **full** band and ask how close the tightest thing in it already
comes to the node row or the rail.

Anything at or above that number is a clearance the book already lives
with, so deflating to it takes no drawing anywhere it has not been.
"""
import common
from symbulator import schematic as sch
from symbulator.elements import parse_circuit


def slack_of(desc, row_h=None):
    els = parse_circuit(desc, expand_si=False)
    if any(e.kind == "t" or e.kind in sch.PORT_BLOCK for e in els):
        return None, None
    lay0 = sch._Layout(els)
    rows = sorted(lay0.op_raised)
    ups = sorted(sch._Layout(els, allow_above=set(
        e.name for e in lay0.opamps)).op_above)
    best, best_cost = (set(), set()), None
    if rows or ups:
        for choice in sch._placements(rows, ups):
            c = sch._cost(sch._render_once(els, None, *choice))
            if best_cost is None or c < best_cost:
                best, best_cost = choice, c
    probe = {}
    sch._render_once(els, None, best[0], best[1], row_h=row_h, out=probe)
    lay, cv = probe["lay"], probe["cv"]
    floor = lay.y_under if lay.op_under else lay.y_bot
    boxes = sch._band_content(cv, lay)
    if not boxes:
        return None, lay
    return min(min(y0 - lay.y_top, floor - y1)
               for _x0, y0, _x1, y1 in boxes), lay


def main():
    rows = []
    for book, i, name, desc in common.entries():
        try:
            s, lay = slack_of(desc, row_h=sch.ROW_H)
        except Exception as ex:                          # noqa: BLE001
            print("FAIL %s [%s]: %s" % (book, name, ex))
            continue
        if s is None:
            continue
        rows.append((round(s, 1), book, name))
    rows.sort()
    print("clearance to the row or the rail at the FULL band, 25 tightest\n")
    for s, book, name in rows[:25]:
        print("  %6.1f  %-18s %s" % (s, book.replace(".cir", ""), name[:52]))
    vals = [r[0] for r in rows]
    n = len(vals)
    print("\n%d drawings (blocks excluded, as the tightening excludes them)"
          % n)
    for p in (0, 1, 2, 5, 10, 25, 50, 75):
        print("   %2d%% percentile: %6.1f" % (p, vals[min(n - 1,
                                                          p * n // 100)]))
    print("   max            : %6.1f" % vals[-1])


if __name__ == "__main__":
    main()
