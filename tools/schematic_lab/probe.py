"""Print every line and dot of one drawing, so a suspicious number can
be looked at instead of believed."""
import sys

import common
import quality


def find(pattern):
    for book, i, name, desc in common.entries():
        if pattern.lower() in ("%s %s" % (book, name)).lower():
            return book, i, name, desc
    raise SystemExit("no entry matching %r" % pattern)


def main(pattern, out=None):
    book, i, name, desc = find(pattern)
    q = quality.measure(desc)
    cap = quality.CAPTURE
    print("%s [%d] %s" % (book, i, name))
    print("desc: %s" % desc)
    print("canvas %.0f x %.0f" % (q["w"], q["h"]))
    print("\n-- wire runs (merged) --")
    for x0, y0, x1, y1 in sorted(cap["hor"]):
        print("  H  y=%7.1f   x %7.1f .. %7.1f   len %6.1f"
              % (y0, x0, x1, x1 - x0))
    for x0, y0, x1, y1 in sorted(cap["ver"]):
        print("  V  x=%7.1f   y %7.1f .. %7.1f   len %6.1f"
              % (x0, y0, y1, y1 - y0))
    print("\n-- element segments (axis + leads; half = body/2) --")
    for x1, y1, x2, y2, half in sorted(cap["esegs"]):
        kind = "H" if abs(y1 - y2) < 0.01 else "V"
        print("  %s  (%7.1f,%7.1f) .. (%7.1f,%7.1f)  half=%5.1f  span=%6.1f"
              % (kind, x1, y1, x2, y2, half,
                 max(abs(x2 - x1), abs(y2 - y1))))
    print("\n-- obstacles (op-amp bodies) --")
    for o in cap["obstacles"]:
        print("  %s" % (tuple(round(v, 1) for v in o),))
    print("\n-- blocks --")
    for o in cap["blocks"]:
        print("  %s" % (tuple(round(v, 1) for v in o),))
    print("\n-- dots (x, y, degree) --")
    for d in sorted(q["stray_dot_detail"]):
        print("  STRAY %s" % (tuple(round(v, 1) for v in d),))
    print("\n-- near-corner joins --")
    for d, a, b in q["near_corner_detail"]:
        print("  %5.1f  (%7.1f,%7.1f) -- (%7.1f,%7.1f)"
              % (d, a[0], a[1], b[0], b[1]))
    print("\n-- crowded pairs (sep, overlap, axis, a, b, from) --")
    for c in q["crowd_detail"]:
        print("  %s" % (c,))
    if out:
        with open(out, "wb") as f:
            f.write(q["svg"].encode("utf-8"))
        print("\nwrote %s" % out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
