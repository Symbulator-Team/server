"""How close two labels come to each other, in a snapshot directory.

The harness asks "do they overlap?" with a 1px tolerance. Roberto's
rule 7 is stronger -- *lines should not be together if they can be
apart* -- and a pair of labels 3px apart passes the harness and still
reads as one smudge. So measure the distance, not the overlap.

Reads the SVGs a snapshot wrote, so it works on any revision without
swapping anything in, and it measures the artefact rather than the
canvas that produced it. Metrics copied from the review harness so the
two agree: 7.3px an advance, subscripts at `SUB_SCALE`.
"""
import json
import os
import re
import sys

TEXT = re.compile(
    r'<text[^>]*x="([-\d.]+)" y="([-\d.]+)" text-anchor="(\w+)">(.*?)</text>')
TSPAN = re.compile(r'<tspan(?P<attrs>[^>]*)>(?P<txt>[^<]*)</tspan>')
CHAR_W = 7.3
SUB_SCALE = 0.72
ASC = 10.0
DESC = 3.25


def boxes(svg):
    out = []
    for m in TEXT.finditer(svg):
        x, y, anchor = float(m.group(1)), float(m.group(2)), m.group(3)
        runs = [(t.group("txt"), 'class="sub"' in t.group("attrs"))
                for t in TSPAN.finditer(m.group(4))]
        if not runs:
            continue
        w = sum(len(t) * (CHAR_W * SUB_SCALE if sub else CHAR_W)
                for t, sub in runs)
        if anchor == "middle":
            x0 = x - w / 2
        elif anchor == "end":
            x0 = x - w
        else:
            x0 = x
        out.append((x0, y - ASC, x0 + w, y + DESC,
                    "".join(t for t, _ in runs)))
    return out


def closest(svg):
    bs = boxes(svg)
    worst = None
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            a, b = bs[i], bs[j]
            if min(a[3], b[3]) - max(a[1], b[1]) <= 0:
                continue                     # not on the same line
            d = max(b[0] - a[2], a[0] - b[2])
            if d < -0.5:
                continue                     # already overlapping
            if worst is None or d < worst[0]:
                worst = (d, a[4], b[4])
    return worst


def survey(d):
    with open(os.path.join(d, "index.json"), "rb") as f:
        idx = json.loads(f.read().decode("utf-8"))
    rows = []
    for r in idx:
        p = os.path.join(d, r["stem"] + ".svg")
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            svg = f.read().decode("utf-8")
        w = closest(svg)
        if w:
            rows.append((round(w[0], 1), r["book"], r["name"], w[1], w[2]))
    rows.sort()
    return rows


def main(*dirs):
    tables = {}
    for d in dirs:
        rows = survey(d)
        tables[d] = rows
        vals = [r[0] for r in rows]
        n = len(vals)
        print("\n== %s ==  %d drawings" % (d, n))
        print("   tightest pairs:")
        for v, book, name, s1, s2 in rows[:8]:
            print("     %6.1f  %-16s %-40s  %r / %r"
                  % (v, book.replace(".cir", ""), name[:40], s1, s2))
        print("   percentiles: " + "  ".join(
            "%d%%=%.1f" % (p, vals[min(n - 1, p * n // 100)])
            for p in (0, 1, 5, 10, 25, 50)))
    if len(dirs) == 2:
        a = {(r[1], r[2]): r[0] for r in tables[dirs[0]]}
        b = {(r[1], r[2]): r[0] for r in tables[dirs[1]]}
        worse = sorted(((b[k] - a[k], k, a[k], b[k]) for k in a if k in b
                        and b[k] < a[k] - 0.5))
        print("\n== %d drawings where labels got closer ==" % len(worse))
        for _d, k, x, y in worse[:15]:
            print("   %-16s %-42s %6.1f -> %6.1f"
                  % (k[0].replace(".cir", ""), k[1][:42], x, y))


if __name__ == "__main__":
    main(*sys.argv[1:])
