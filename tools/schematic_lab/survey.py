"""Measure all 356 drawings and dump the numbers.

Writes survey.json (one record per entry, no SVG) and prints the
distribution of each of the seven values, worst first -- so an
implausible number is visible as an outlier rather than hiding in an
average.
"""
import json
import sys

import common
import quality

KEYS = ["crossings", "bends", "wires", "near_corner", "dots", "stray_dots",
        "slack_total", "slack_per_elem", "slack_max", "area_per_elem",
        "crowd", "w", "h", "n_elem", "rows", "n_h", "cols", "n_v"]


def run(path="survey.json"):
    rows = []
    for book, i, name, desc in common.entries():
        try:
            q = quality.measure(desc)
        except Exception as ex:                       # noqa: BLE001
            print("FAIL %s [%s]: %s" % (book, name, ex))
            continue
        rec = {"book": book, "index": i, "name": name, "desc": desc}
        for k in KEYS:
            rec[k] = q[k]
        rec["crowd_worst"] = q["crowd_worst"]
        rec["near_corner_detail"] = [
            [d, list(a), list(b)] for d, a, b in q["near_corner_detail"]]
        rec["stray_dot_detail"] = [list(d) for d in q["stray_dot_detail"]]
        rec["crowd_detail"] = [list(c) for c in q["crowd_detail"]]
        rec["slack_detail"] = [list(s) for s in q["slack_detail"]]
        rows.append(rec)
    with open(path, "wb") as f:
        f.write(json.dumps(rows, indent=1).encode("utf-8"))
    return rows


def report(rows):
    def top(key, n=12, reverse=True):
        rs = sorted(rows, key=lambda r: (r[key] is None, r[key]),
                    reverse=reverse)
        print("\n== %s, worst %d ==" % (key, n))
        for r in rs[:n]:
            print("   %6s  %-18s %-46s %.0fx%.0f"
                  % (r[key], r["book"].replace(".cir", ""),
                     r["name"][:46], r["w"], r["h"]))

    print("%d drawings" % len(rows))
    for key in ("crossings", "near_corner", "stray_dots", "crowd",
                "slack_max", "area_per_elem", "bends"):
        vals = [r[key] for r in rows]
        nz = sum(1 for v in vals if v)
        print("  %-14s nonzero %3d/%d   max %-8s mean %.1f"
              % (key, nz, len(vals), max(vals), sum(vals) / len(vals)))
    for key in ("crossings", "near_corner", "stray_dots", "crowd",
                "slack_max", "area_per_elem"):
        top(key)


if __name__ == "__main__":
    rows = run(sys.argv[1] if len(sys.argv) > 1 else "survey.json")
    report(rows)
