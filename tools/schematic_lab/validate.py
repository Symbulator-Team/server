"""Does the objective order these drawings the way Roberto did?

The ground truth is the 22 drawings that moved between #366 and the
released 0.6.4. He reviewed all 63 op-amp drawings after that change and
named exactly two for fine-tuning (#371) and four crossings as
unavoidable -- so for these 22, the *after* is the state he ruled on and
the *before* is what he replaced.

That makes each of them a pair with a known answer. An objective that
prefers the "before" on one of them is wrong, or the case is
mislabelled -- and the retiring session's note says that happened once,
so check the picture before believing either.

Run `validate.py <before.json> <after.json>`.
"""
import json
import sys

TERMS = ["crossings", "bends", "near_corner", "stray_dots", "crowd",
         "slack_total", "area_per_elem", "wires"]


def load(p):
    with open(p, "rb") as f:
        rows = json.loads(f.read().decode("utf-8"))
    return {(r["book"], r["index"]): r for r in rows}


def main(before, after):
    a, b = load(before), load(after)
    pairs = [k for k in sorted(a) if k in b
             and any(a[k][t] != b[k][t] for t in TERMS
                     + ["w", "h"])]
    print("%d drawings differ on at least one measure\n" % len(pairs))
    head = "%-18s %-42s" % ("book", "name") + "".join(
        "%12s" % t[:11] for t in TERMS)
    print(head)
    print("-" * len(head))
    worse = {t: [] for t in TERMS}
    for k in pairs:
        ra, rb = a[k], b[k]
        cells = []
        for t in TERMS:
            va, vb = ra[t], rb[t]
            if va == vb:
                cells.append("%12s" % "=")
            else:
                cells.append("%12s" % ("%g>%g" % (va, vb)))
                if vb > va:
                    worse[t].append((k, ra["name"], va, vb))
        print("%-18s %-42s%s" % (k[0].replace(".cir", ""),
                                 rb["name"][:42], "".join(cells)))
    print("\n== where the state he ruled on scores WORSE ==")
    for t in TERMS:
        if not worse[t]:
            continue
        print("  %s: %d" % (t, len(worse[t])))
        for k, name, va, vb in worse[t]:
            print("      %-18s %-44s %g -> %g"
                  % (k[0].replace(".cir", ""), name[:44], va, vb))
    for t in TERMS:
        if not worse[t]:
            print("  %s: none -- the ruling never costs on this term" % t)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
