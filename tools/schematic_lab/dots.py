"""Junction dots, and how close together they sit.

Roberto, 11 Sep 2026: *"Avoiding nearby dots. Where there are two nearby
dots, there should be an incentive to merge them."*

Two traps in counting them, both of which this walked into first:

  * **a `<circle>` is not a dot.** An independent source's outline is a
    circle too, and a coupling dot is drawn inside a symbol's own
    group. A junction dot is the one `_flush_wires` emits, with
    `fill="currentColor"`, outside every group -- so the group
    stripping that `quality.py` needs for wires is needed here as well.
  * **a dot is not always a junction.** A coupling dot on a mutual
    inductance, and a transformer's polarity dots, are the same shape
    saying a different thing. Those live inside `<g transform=...>`
    groups and drop out with the stripping above.
"""
import math
import re
import sys

import common
from symbulator import schematic as sch

GROUP = re.compile(r"<g transform=.*?</g>", re.S)
DOT = re.compile(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="([-\d.]+)" '
                 r'fill="currentColor"')


def dots_of(svg):
    body = GROUP.sub("", svg)
    return [(float(x), float(y)) for x, y, _r in DOT.findall(body)]


def closest(dots):
    worst = None
    for a in range(len(dots)):
        for b in range(a + 1, len(dots)):
            d = math.hypot(dots[a][0] - dots[b][0], dots[a][1] - dots[b][1])
            if worst is None or d < worst[0]:
                worst = (d, dots[a], dots[b])
    return worst


def main(pattern=None, near=40.0):
    rows = []
    total = 0
    for book, i, name, desc in common.entries():
        if pattern and pattern.lower() not in ("%s %s" % (book, name)).lower():
            continue
        d = dots_of(sch.to_svg(desc))
        total += len(d)
        w = closest(d)
        pairs = sum(1 for a in range(len(d)) for b in range(a + 1, len(d))
                    if math.hypot(d[a][0] - d[b][0],
                                  d[a][1] - d[b][1]) < near)
        rows.append((w[0] if w else 1e9, pairs, len(d), book, name, w))
    rows.sort()
    print("%d drawings, %d junction dots\n" % (len(rows), total))
    n_near = sum(1 for r in rows if r[1])
    print("   drawings with a pair closer than %.0fpx : %d" % (near, n_near))
    print("   pairs closer than %.0fpx in total        : %d\n"
          % (near, sum(r[1] for r in rows)))
    print("%8s %6s %5s  %-16s %s"
          % ("closest", "pairs", "dots", "book", "name"))
    for c, pairs, nd, book, name, w in rows[:25]:
        if c > near:
            break
        print("%8.1f %6d %5d  %-16s %s"
              % (c, pairs, nd, book.replace(".cir", ""), name[:46]))
        if pattern and w:
            print("           between (%.1f, %.1f) and (%.1f, %.1f)"
                  % (w[1][0], w[1][1], w[2][0], w[2][1]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None,
         float(sys.argv[2]) if len(sys.argv) > 2 else 40.0)
