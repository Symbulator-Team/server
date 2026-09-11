"""How close does a label come to a line that is not its own?

Roberto, 11 Sep 2026, on Bo2's Example 5.5: *"the label of R2 is too
close to the line that goes from 0 to the positive input of the op-amp.
Labels should not be so close to lines unrelated to them."*

A label may sit close to its **own** element -- `GAP` is exactly that,
4px of clear air between a symbol's ink and its label. The complaint is
about everything else. So the question needs the label to know whose it
is, which is what `_Canvas.label_owner` records: the axis of the element
that drew it, or `None` for a node name, a ground name or a caption.

Labels with no owner are skipped. A node name is placed 6px from its own
column on purpose, and calling that a violation would be measuring
something other than the complaint.
"""
import sys

import common
from symbulator import schematic as sch

_EPS = 0.01


def worst_of(desc):
    """(clearance, label box, the line) for the tightest unrelated pair."""
    cv_box = {}

    orig = sch._Canvas.flush

    def flush(self):
        cv_box["cv"] = self
        return orig(self)

    sch._Canvas.flush = flush
    try:
        sch.to_svg(desc)
    finally:
        sch._Canvas.flush = orig
    cv = cv_box["cv"]

    lines = [w[:4] for w in cv.wires] + [s[:4] for s in cv.esegs]
    worst = None
    for box, own in zip(cv.labels, cv.label_owner):
        if own is None:
            continue
        lx0, ly0, lx1, ly1 = box
        for x1, y1, x2, y2 in lines:
            # Compared as unordered pairs: the canvas normalises a
            # segment's endpoints, the owner tuple keeps the declared
            # order, and matching them literally measures an element
            # against its own axis whenever n1 is at the far end.
            if abs(min(x1, x2) - min(own[0], own[2])) < 0.5 \
                    and abs(min(y1, y2) - min(own[1], own[3])) < 0.5 \
                    and abs(max(x1, x2) - max(own[0], own[2])) < 0.5 \
                    and abs(max(y1, y2) - max(own[1], own[3])) < 0.5:
                continue                       # its own element's axis
            if abs(y1 - y2) < _EPS:            # horizontal line
                lo, hi = min(x1, x2), max(x1, x2)
                if hi < lx0 or lo > lx1:
                    continue
                d = max(ly0 - y1, y1 - ly1)
            elif abs(x1 - x2) < _EPS:          # vertical line
                lo, hi = min(y1, y2), max(y1, y2)
                if hi < ly0 or lo > ly1:
                    continue
                d = max(lx0 - x1, x1 - lx1)
            else:
                continue
            if worst is None or d < worst[0]:
                worst = (d, box, (x1, y1, x2, y2))
    return worst


def main(pattern=None):
    rows = []
    for book, i, name, desc in common.entries():
        if pattern and pattern.lower() not in ("%s %s" % (book, name)).lower():
            continue
        try:
            w = worst_of(desc)
        except Exception as ex:                        # noqa: BLE001
            print("FAIL %s: %s" % (name, ex))
            continue
        if w:
            rows.append((round(w[0], 1), book, name, w))
    rows.sort()
    print("tightest label-to-unrelated-line clearance, per drawing\n")
    print("%8s  %-16s %s" % ("gap", "book", "name"))
    for d, book, name, w in rows[:22]:
        print("%8.1f  %-16s %s" % (d, book.replace(".cir", ""), name[:48]))
        if pattern:
            print("           label box %s   line %s"
                  % (tuple(round(v, 1) for v in w[1]),
                     tuple(round(v, 1) for v in w[2])))
    vals = [r[0] for r in rows]
    n = len(vals)
    print("\n%d drawings with at least one owned label" % n)
    for p in (0, 1, 2, 5, 10, 25, 50):
        print("   %2d%% : %6.1f" % (p, vals[min(n - 1, p * n // 100)]))
    for t in (6, 8, 10, 12, 16):
        print("   closer than %2d px: %3d drawings"
              % (t, sum(1 for v in vals if v < t)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
