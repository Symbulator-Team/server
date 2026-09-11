"""Which two boxes make a drawing's tightest gap. Evidence, not a number."""
import sys

import common
import quality


def main(pattern):
    for book, i, name, desc in common.entries():
        if pattern.lower() not in ("%s %s" % (book, name)).lower():
            continue
        quality.measure(desc)
        lay = quality.LAYOUT["lay"]
        cap = quality.CAPTURE
        y_top, y_bot = lay.y_top, lay.y_bot
        print("%s [%d] %s   band %.1f .. %.1f" % (book, i, name, y_top, y_bot))
        boxes = []
        for tag, lst in (("ink", cap["inks"]), ("obst", cap["obstacles"]),
                         ("blk", cap["blocks"])):
            for x0, y0, x1, y1 in lst:
                if y1 <= y_top + 0.5 or y0 >= y_bot - 0.5:
                    continue
                boxes.append((tag, x0, y0, x1, y1))
        for tag, x0, y0, x1, y1 in sorted(boxes, key=lambda b: (b[1], b[2])):
            print("   %-5s x %7.1f..%7.1f  y %7.1f..%7.1f  (%.1f tall)"
                  % (tag, x0, x1, y0, y1, y1 - y0))
        best = None
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                p, q = boxes[a], boxes[b]
                if p[3] <= q[1] + 0.5 or q[3] <= p[1] + 0.5:
                    continue
                g = max(q[2] - p[4], p[2] - q[4])
                if g > 0.5 and (best is None or g < best[0]):
                    best = (g, p, q)
        if best:
            print("   tightest pair gap %.1f between\n      %s\n      %s"
                  % (best[0], best[1], best[2]))
        print()
        return


if __name__ == "__main__":
    main(sys.argv[1])
