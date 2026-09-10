"""Which drawings moved between two snapshots. Byte comparison."""
import json
import os
import sys


def load(d):
    with open(os.path.join(d, "index.json"), "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def read(d, stem):
    p = os.path.join(d, stem + ".svg")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def main(a, b, verbose=False):
    ia, ib = load(a), load(b)
    key = lambda r: (r["book"], r["index"])            # noqa: E731
    ma = {key(r): r for r in ia}
    mb = {key(r): r for r in ib}
    moved, same, gone = [], 0, []
    for k in sorted(set(ma) | set(mb)):
        ra, rb = ma.get(k), mb.get(k)
        if ra is None or rb is None:
            gone.append(k)
            continue
        sa, sb = read(a, ra["stem"]), read(b, rb["stem"])
        if sa == sb:
            same += 1
        else:
            moved.append((k, rb["name"], len(sa or b""), len(sb or b"")))
    print("moved=%d unchanged=%d missing=%d" % (len(moved), same, len(gone)))
    for (book, i), name, la, lb in moved:
        print("  %-20s %3d  %-52s %6d -> %6d" % (book, i, name[:52], la, lb))
    return moved


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
