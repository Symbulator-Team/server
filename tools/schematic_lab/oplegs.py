"""The two input leads of every op-amp, measured and paired with their
own polarity mark.

Roberto, 11 Sep 2026: *"the negative leg of the op-amp tends to be
longer than the positive leg. Is that a design decision? I'd very much
like both legs to be the same length whenever there is no good reason
for them to be different."*

The polarity is read off `_sign_mark` -- the call that actually draws
the + or the - -- so the pairing cannot drift from the picture. The lead
is the horizontal wire with one end **on the body's face** at that pin's
height.

Two things the first version of this got wrong, both worth keeping in
mind for anything that hooks the drawer:

  * `_render` draws every candidate layout and keeps the cheapest, so a
    module-level list accumulates every pass. Marks and wires are kept
    **per canvas** here, and the winner is the last canvas made.
  * the lead is not "the longest horizontal wire at that height". It is
    the one touching the face. Taking the longest picked up the node
    row and reported a 187px leg.
"""
import sys

import common
from symbulator import schematic as sch
from symbulator.elements import parse_circuit

CANVASES = []


def install():
    if getattr(sch, "_oplegs_hooked", False):
        return
    orig_mark = sch._sign_mark
    orig_wire = sch._Canvas.wire
    orig_init = sch._Canvas.__init__

    def init(self, *a, **kw):
        orig_init(self, *a, **kw)
        self._marks = []
        self._wires = []
        CANVASES.append(self)

    # `_sign_mark` draws a *voltage source's* polarity marks as well as
    # an op-amp's pins -- deliberately, since #130 made the pin signs
    # the same stroked marks. So only the marks made while
    # `_draw_opamp` is running are pins. Without this the book reports
    # 78 op-amps where it has 63, every source pair counted as one.
    depth = [0]

    def mark(cv, x, y, plus):
        if depth[0]:
            cv._marks.append((x, y, plus))
        return orig_mark(cv, x, y, plus)

    orig_draw = sch._draw_opamp

    def draw_opamp(cv, lay, e):
        depth[0] += 1
        try:
            return orig_draw(cv, lay, e)
        finally:
            depth[0] -= 1

    sch._draw_opamp = draw_opamp

    def wire(self, x1, y1, x2, y2):
        self._wires.append((x1, y1, x2, y2))
        return orig_wire(self, x1, y1, x2, y2)

    sch._Canvas.__init__ = init
    sch._sign_mark = mark
    sch._Canvas.wire = wire
    sch._oplegs_hooked = True


def legs(desc):
    """[(sign, length, y)] for every op-amp pin of the winning drawing."""
    install()
    CANVASES.clear()
    sch.to_svg(desc)
    cv = CANVASES[-1]
    out = []
    for mx, my, plus in cv._marks:
        face = mx - 13.0            # `_sign_mark(cv, tx + 13, ...)`
        best = None
        for x1, y1, x2, y2 in cv._wires:
            if abs(y1 - y2) > 0.01 or abs(y1 - my) > 0.01:
                continue
            lo, hi = min(x1, x2), max(x1, x2)
            if hi - lo < 0.5:
                continue
            if abs(lo - face) > 1 and abs(hi - face) > 1:
                continue            # not touching the body's face
            if best is None or hi - lo < best[0]:
                best = (hi - lo, lo, hi)
        if best:
            out.append(("+" if plus else "-", round(best[0], 1), round(my, 1)))
    return out


def pairs(desc):
    """[(upper, lower)] per op-amp, each `(sign, length, y)`.

    The pin higher on the page first. Which of the two is the inverting
    input depends on the circuit's orientation, so the interesting
    question is not "is the minus longer" but "is the same *pin* always
    longer" -- and that one has a single answer."""
    ls = legs(desc)
    out = []
    for k in range(0, len(ls) - 1, 2):
        a, b = ls[k], ls[k + 1]
        if a[0] == b[0]:
            continue
        upper, lower = (a, b) if a[2] < b[2] else (b, a)
        out.append((upper, lower))
    return out


def main(pattern=None):
    rows = []
    odd = 0
    for book, i, name, desc in common.entries():
        if pattern and pattern.lower() not in ("%s %s" % (book, name)).lower():
            continue
        els = parse_circuit(desc, expand_si=False)
        if not any(e.kind == "o" for e in els):
            continue
        try:
            ls = legs(desc)
        except Exception as ex:                        # noqa: BLE001
            print("FAIL %s: %s" % (name, ex))
            continue
        if len(ls) % 2:
            odd += 1
            continue
        for k in range(0, len(ls), 2):
            a, b = ls[k], ls[k + 1]
            if a[0] == b[0]:
                continue
            plus = a if a[0] == "+" else b
            minus = b if a[0] == "+" else a
            rows.append((round(minus[1] - plus[1], 1), book, name,
                         plus[1], minus[1]))
    rows.sort()
    same = sum(1 for r in rows if abs(r[0]) < 0.5)
    longer = sum(1 for r in rows if r[0] > 0.5)
    shorter = sum(1 for r in rows if r[0] < -0.5)
    print("%d op-amps, %d drawings skipped for an odd pin count\n"
          % (len(rows), odd))
    print("   minus leg LONGER than plus : %3d" % longer)
    print("   the two the SAME length    : %3d" % same)
    print("   minus leg SHORTER          : %3d" % shorter)
    from collections import Counter
    print("\n   differences, most common first:")
    for d, n in Counter(r[0] for r in rows).most_common(12):
        print("      %+8.1f px : %3d op-amps" % (d, n))
    if pattern:
        print("\n%8s %8s %8s  %s" % ("diff", "plus", "minus", "name"))
        for d, book, name, p, m in rows:
            print("%8.1f %8.1f %8.1f  %s" % (d, p, m, name[:52]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
