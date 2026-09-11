"""The objective, and the evidence for its shape.

Nothing here is invented. Each candidate ordering below is scored
against the 22 drawings Roberto ruled on when he accepted 0.6.4 -- the
"after" is his ruling, so an ordering that calls the "after" worse is
wrong. Run it and read the constraint list: it says which terms the
data can order and which it cannot.

The comparison is lexicographic on a tuple, which is what "every bend
costs money, and every cross costs a lot of money" already meant in
`_cost`: no number of saved bends buys one more crossing.
"""
import json
import sys

# Every candidate ordering worth asking about. Each is a list of term
# names; a term prefixed "-" is one where MORE is better (none so far).
CANDIDATES = {
    "shipped (#372)": ["crossings", "bends", "wires"],
    "+ joins after bends": ["crossings", "bends", "joins", "crowd", "wires"],
    "+ joins before bends": ["crossings", "joins", "bends", "crowd", "wires"],
    "+ crowd before bends": ["crossings", "crowd", "bends", "joins", "wires"],
    "size first": ["area_per_elem", "crossings", "bends"],
    "size after bends": ["crossings", "bends", "area_per_elem"],
    "size last": ["crossings", "bends", "joins", "crowd", "wires",
                  "area_per_elem"],
    "slack after bends": ["crossings", "bends", "slack_total"],
}


def terms(r):
    """The measures, plus the two derived ones the candidates name."""
    d = dict(r)
    # A join that lies about the topology: a lead teeing in near a
    # corner, and a dot claiming a meeting the picture does not show.
    # They are two views of one defect (see `quality.py`), so they are
    # summed rather than ordered against each other.
    d["joins"] = r["near_corner"] + r["stray_dots"]
    return d


def load(p):
    with open(p, "rb") as f:
        rows = json.loads(f.read().decode("utf-8"))
    return {(r["book"], r["index"]): terms(r) for r in rows}


def key(r, order):
    return tuple(r[t] for t in order)


def main(before, after):
    a, b = load(before), load(after)
    keys = [k for k in sorted(a) if k in b]
    pairs = [k for k in keys if key(a[k], sorted(set(
        t for o in CANDIDATES.values() for t in o))) !=
        key(b[k], sorted(set(t for o in CANDIDATES.values() for t in o)))]
    print("%d pairs where any measure differs\n" % len(pairs))
    print("%-24s %6s %6s %6s   %s" % ("ordering", "right", "wrong", "tie",
                                      "the ones it calls wrong"))
    print("-" * 100)
    for label, order in CANDIDATES.items():
        right = wrong = tie = 0
        bad = []
        for k in pairs:
            ka, kb = key(a[k], order), key(b[k], order)
            if kb < ka:
                right += 1
            elif kb > ka:
                wrong += 1
                bad.append(b[k]["name"][:34])
            else:
                tie += 1
        print("%-24s %6d %6d %6d   %s"
              % (label, right, wrong, tie, "; ".join(bad[:3])))

    # --- what the data can actually order ----------------------------
    # For every pair the ruling improved on term X and worsened on term
    # Y, X must outrank Y. Collect those implications.
    names = ["crossings", "bends", "joins", "near_corner", "stray_dots",
             "crowd", "wires", "slack_total", "area_per_elem"]
    implies = {}
    for k in pairs:
        better = [t for t in names if b[k][t] < a[k][t]]
        worse = [t for t in names if b[k][t] > a[k][t]]
        for x in better:
            for y in worse:
                implies.setdefault((x, y), []).append(b[k]["name"][:40])
    print("\n== what his rulings force: X must outrank Y ==")
    seen = set()
    for (x, y), why in sorted(implies.items()):
        if (y, x) in implies:
            if (y, x) in seen:
                continue
            seen.add((x, y))
            print("  CONTRADICTION  %s vs %s -- %d and %d cases both ways"
                  % (x, y, len(why), len(implies[(y, x)])))
            continue
        print("  %-14s > %-14s  (%d case%s, e.g. %s)"
              % (x, y, len(why), "" if len(why) == 1 else "s", why[0]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
