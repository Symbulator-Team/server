"""How much of each column gap is air.

The vertical half of the balloon is one number per drawing; the
horizontal half is one per *gap*, because `px(col) = MARGIN + col *
COL_W` gives every gap the same 132px whether it carries a stretched
resistor with a two-line label or nothing but a wire.

Measured the same way as the band: render, then ask what actually
stands in each gap. An object counts against the gap its centre falls
in, and its half-width says how much of that gap it claims. A body
stretched across several gaps is charged to the gaps it spans.
"""
import common
from symbulator import schematic as sch
from symbulator.elements import parse_circuit


def gaps_of(desc):
    els = parse_circuit(desc, expand_si=False)
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
    sch._render_once(els, None, best[0], best[1], out=probe)
    lay, cv = probe["lay"], probe["cv"]
    cols = sorted(set(lay.node_col.values()) | set(lay.elem_col.values()))
    if len(cols) < 2:
        return None
    xs = [lay.px(c) for c in cols]
    boxes = list(cv.inks) + list(cv.labels) + list(cv.obstacles)
    out = []
    for i in range(len(xs) - 1):
        lo, hi = xs[i], xs[i + 1]
        width = hi - lo
        need = 0.0
        for x0, _y0, x1, _y1 in boxes:
            if x1 <= lo + 0.5 or x0 >= hi - 0.5:
                continue
            need = max(need, min(x1, hi) - max(x0, lo))
        out.append((round(width, 1), round(need, 1), round(width - need, 1)))
    return out


def main():
    rows = []
    for book, i, name, desc in common.entries():
        try:
            gs = gaps_of(desc)
        except Exception as ex:                          # noqa: BLE001
            print("FAIL %s [%s]: %s" % (book, name, ex))
            continue
        if not gs:
            continue
        rows.append((book, name, gs))
    allgaps = [g for _b, _n, gs in rows for g in gs]
    print("%d drawings, %d column gaps\n" % (len(rows), len(allgaps)))
    air = sorted(g[2] for g in allgaps)
    n = len(air)
    print("air per gap (gap width minus the widest thing standing in it):")
    for p in (0, 5, 10, 25, 50, 75, 90, 100):
        print("   %3d%% : %6.1f" % (p, air[min(n - 1, p * n // 100)]))
    empty = sum(1 for g in allgaps if g[1] < 1.0)
    print("\n   %d of %d gaps (%.0f%%) carry nothing at all"
          % (empty, n, 100.0 * empty / n))
    print("   %d carry something narrower than 60px"
          % sum(1 for g in allgaps if g[1] < 60))
    print("   %d carry something wider than 100px"
          % sum(1 for g in allgaps if g[1] > 100))
    # What the drawing would measure if every gap shrank to its content
    # plus the smallest clearance the book already shows.
    for clear in (12, 20, 28, 36):
        tot = sum(g[0] for g in allgaps)
        new = sum(max(60.0, g[1] + 2 * clear) for g in allgaps)
        print("   clearance %2d -> total gap width %.0f%% of today"
              % (clear, 100.0 * new / tot))


if __name__ == "__main__":
    main()
