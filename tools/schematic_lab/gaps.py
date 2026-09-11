"""The vertical gaps that already exist inside the band.

If the band is going to deflate, the floor it stops at should be a
number the book already lives with, not one fitted to make a drawing
Roberto complained about look better. So: measure every vertical gap in
the band on all 356 drawings as they are shipped today, and read the
floor off the distribution.

A gap is measured three ways, because a body can be crowded by three
things: the node row above it, the ground rail below it, and another
body in its own column.

Shrinking the band by `delta` closes every one of these by `delta/2` --
each body hangs at the band's midpoint or at a lane offset from the top,
and the rail moves by the whole `delta`, so the arithmetic comes out the
same either side. That is what makes one number per drawing enough.
"""
import sys

import common
import quality


def bodies_in_band(cap, y_top, y_bot):
    """The separate things standing in the band, one box each.

    Two collapses, both of them one object being reported twice:

      * an op-amp draws its wedge as `OP_INK_BANDS` = 24 horizontal
        strips, so consecutive strips of one triangle sit 2.4px apart
        and an unguarded pair test calls that the tightest gap in the
        drawing -- on every op-amp drawing in the book;
      * a body that is also a keep-out reports both, over the same
        rectangle.

    Anything inside an obstacle or a block belongs to it. What is left
    is merged where the boxes touch and share a column.
    """
    keep = [b for b in cap["obstacles"] + cap["blocks"]]
    loose = []
    for x0, y0, x1, y1 in cap["inks"]:
        if any(bx0 - 1 <= x0 and x1 <= bx1 + 1
               and by0 - 1 <= y0 and y1 <= by1 + 1
               for bx0, by0, bx1, by1 in keep):
            continue                       # that body's own ink
        loose.append([x0, y0, x1, y1])
    merged = []
    for b in sorted(loose, key=lambda b: (b[0], b[1])):
        for m in merged:
            if b[0] <= m[2] + 1 and m[0] <= b[2] + 1 \
                    and b[1] <= m[3] + 1 and m[1] <= b[3] + 1:
                m[0], m[1] = min(m[0], b[0]), min(m[1], b[1])
                m[2], m[3] = max(m[2], b[2]), max(m[3], b[3])
                break
        else:
            merged.append(list(b))
    out = []
    for x0, y0, x1, y1 in [tuple(m) for m in merged] + keep:
        if y1 <= y_top + 0.5 or y0 >= y_bot - 0.5:
            continue
        out.append((x0, y0, x1, y1))
    return out


def gaps_of(desc):
    quality.measure(desc)
    lay = quality.LAYOUT["lay"]
    cap = quality.CAPTURE
    y_top, y_bot = lay.y_top, lay.y_bot
    boxes = bodies_in_band(cap, y_top, y_bot)
    out = []
    for x0, y0, x1, y1 in boxes:
        out.append((round(y0 - y_top, 1), "row", round(x0)))
        out.append((round(y_bot - y1, 1), "rail", round(x0)))
    # Two bodies sharing a column: the gap between them counts too --
    # but only where they are two *different* things. An op-amp reports
    # its triangle as ink and again as an obstacle over the same
    # rectangle, so an unguarded pair test measures the body against
    # itself and returns 0.0 on every op-amp drawing in the book. That
    # was the first version's answer, and 0.0 on 30 drawings Roberto
    # calls fine is what an implausible number looks like.
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[2] <= b[0] + 0.5 or b[2] <= a[0] + 0.5:
                continue                      # no overlap in x
            g = max(b[1] - a[3], a[1] - b[3])
            if g > 0.5:
                out.append((round(g, 1), "pair", round(a[0])))
    return [g for g in out if g[0] > 0.5]


def main():
    rows = []
    for book, i, name, desc in common.entries():
        try:
            gs = gaps_of(desc)
        except Exception as ex:                       # noqa: BLE001
            print("FAIL %s [%s]: %s" % (book, name, ex))
            continue
        if not gs:
            continue
        g, kind, x = min(gs)
        rows.append((g, kind, book, name, x))
    rows.sort()
    print("tightest vertical gap in the band, per drawing -- 30 tightest\n")
    print("%8s %6s  %-18s %s" % ("gap", "against", "book", "name"))
    for g, kind, book, name, x in rows[:30]:
        print("%8.1f %6s  %-18s %s"
              % (g, kind, book.replace(".cir", ""), name[:50]))
    vals = [r[0] for r in rows]
    n = len(vals)
    print("\n%d drawings" % n)
    for p in (0, 1, 2, 5, 10, 25, 50):
        print("   %2d%% percentile: %6.1f" % (p, vals[min(n - 1, p * n // 100)]))
    print("   max            : %6.1f" % vals[-1])


if __name__ == "__main__":
    main()
