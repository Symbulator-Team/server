"""How much of the band between the node row and the ground rail is air.

Roberto, 10 Sep 2026, on Bo2's Drill Exercise 3.2: the band is 202px --
`ROW_H` 150 plus a 52px under-run band -- and into it hang a 30px source
and a 46px zigzag, so the source has about 156px of bare lead stretched
around it. `ROW_H` is a constant, so the band never shrinks when nothing
needs the room. *The balloon only inflates; it should also deflate.*

This measures the artefact rather than the constant: for every drawing,
the band's height against the tallest ink actually inside it. The ink
list is what each symbol reports drawing (`_Canvas.ink`), so this is
the picture, not a model of it.
"""
import sys

import common
import quality


def band_of(desc):
    q = quality.measure(desc)
    lay = quality.LAYOUT["lay"]
    cap = quality.CAPTURE
    y_top, y_bot = lay.y_top, lay.y_bot
    band = y_bot - y_top
    # Ink drawn inside the band, and how tall the tallest piece is.
    tall = 0.0
    pieces = []
    for x0, y0, x1, y1 in cap["inks"]:
        if y1 <= y_top + 0.5 or y0 >= y_bot - 0.5:
            continue
        h = min(y1, y_bot) - max(y0, y_top)
        if h > tall:
            tall = h
        pieces.append((round(h, 1), round(x0), round(y0), round(y1)))
    # An op-amp body is an obstacle, not ink -- it reports its own box.
    for x0, y0, x1, y1 in cap["obstacles"] + cap["blocks"]:
        if y1 <= y_top + 0.5 or y0 >= y_bot - 0.5:
            continue
        h = min(y1, y_bot) - max(y0, y_top)
        tall = max(tall, h)
        pieces.append((round(h, 1), round(x0), round(y0), round(y1)))
    return {
        "band": round(band, 1),
        "tall": round(tall, 1),
        "air": round(band - tall, 1),
        "y_top": round(y_top, 1), "y_bot": round(y_bot, 1),
        "max_level": lay.max_level,
        "op_lanes": lay.max_op_lane,
        "block_lanes": lay.max_block_lane,
        "op_under": lay.op_under,
        "has_above": lay.has_above,
        "w": q["w"], "h": q["h"],
        "pieces": sorted(pieces, reverse=True)[:4],
    }


def main(pattern=None):
    rows = []
    for book, i, name, desc in common.entries():
        if pattern and pattern.lower() not in ("%s %s" % (book, name)).lower():
            continue
        try:
            b = band_of(desc)
        except Exception as ex:                       # noqa: BLE001
            print("FAIL %s [%s]: %s" % (book, name, ex))
            continue
        b.update(book=book, index=i, name=name)
        rows.append(b)
    rows.sort(key=lambda r: -r["air"])
    print("%-18s %-44s %6s %6s %6s  %s"
          % ("book", "name", "band", "tall", "air", "flags"))
    print("-" * 108)
    for r in rows[:40] if not pattern else rows:
        flags = []
        if r["op_under"]:
            flags.append("under")
        if r["has_above"]:
            flags.append("above")
        if r["op_lanes"]:
            flags.append("oplane%d" % r["op_lanes"])
        if r["block_lanes"]:
            flags.append("blk%d" % r["block_lanes"])
        print("%-18s %-44s %6.0f %6.0f %6.0f  %s"
              % (r["book"].replace(".cir", ""), r["name"][:44],
                 r["band"], r["tall"], r["air"], ",".join(flags)))
        if pattern:
            print("      tallest pieces (h, x, y0, y1): %s" % (r["pieces"],))
    if not pattern:
        air = [r["air"] for r in rows]
        print("\n%d drawings   air: min %.0f  median %.0f  max %.0f"
              % (len(air), min(air), sorted(air)[len(air) // 2], max(air)))
        for lo, hi in ((0, 60), (60, 100), (100, 140), (140, 200), (200, 1e9)):
            n = sum(1 for a in air if lo <= a < hi)
            print("   air %3d-%-4s : %3d drawings" % (lo, hi if hi < 1e9
                                                      else "+", n))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
