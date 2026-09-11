"""Roberto's seven values, measured over a finished drawing.

Read off the canvas, not the SVG text. Every line the reader sees is
either a merged wire run or an element's own axis segment, and the
canvas holds both in one coordinate frame -- which is the whole of the
`<g transform=...>` trap: a symbol draws its leads in its own frame, so
anything measured from the SVG mixes frames and invents geometry.

Each measure is named for what it counts and returns the *evidence*
beside the number, so a suspicious value can be looked at rather than
believed. Two of the prototypes this replaces returned implausibly
large numbers on drawings Roberto calls good; a metric that cannot show
its working cannot be checked.
"""
import math
import re

import common

_EPS = 0.01
NEAR_CORNER = 30.0     # #371's threshold: a join this close to a corner
# reads as a corner the drawing missed
CROWD_SEP = 40.0       # two parallel lines closer than this look joined


def _merge(runs, key_i, lo_i, hi_i):
    """Overlapping collinear runs as one -- `_flush_wires`'s own rule."""
    merged = []
    for r in sorted(runs, key=lambda r: (r[key_i], r[lo_i])):
        for m in merged:
            if abs(m[key_i] - r[key_i]) < _EPS \
                    and r[lo_i] <= m[hi_i] + _EPS \
                    and m[lo_i] <= r[hi_i] + _EPS:
                m[lo_i] = min(m[lo_i], r[lo_i])
                m[hi_i] = max(m[hi_i], r[hi_i])
                break
        else:
            merged.append(list(r))
    return [tuple(m) for m in merged]


CAPTURE = {}


def install():
    """Hook the canvas. The winner is the last drawing flushed, which is
    why `_render` draws it again -- see its docstring."""
    from symbulator import schematic as sch
    if getattr(sch._Canvas, "_quality_hooked", False):
        return sch
    orig_flush = sch._Canvas._flush_wires
    orig_raw = sch._Canvas.raw

    def raw(self, s, *bounds):
        if s.lstrip().startswith("<rect") and len(bounds) == 2:
            (x0, y0), (x1, y1) = bounds
            if not hasattr(self, "_blocks"):
                self._blocks = []
            self._blocks.append((x0, y0, x1, y1))
        return orig_raw(self, s, *bounds)

    def flush(self):
        hor = _merge([w for w in self.wires if abs(w[1] - w[3]) < _EPS],
                     1, 0, 2)
        ver = _merge([w for w in self.wires if abs(w[0] - w[2]) < _EPS],
                     0, 1, 3)
        CAPTURE.clear()
        CAPTURE.update({
            "hor": hor, "ver": ver,
            "esegs": list(self.esegs),
            "obstacles": list(self.obstacles),
            "blocks": list(getattr(self, "_blocks", [])),
            "inks": list(self.inks),
            "labels": list(getattr(self, "labels", ())),
        })
        r = orig_flush(self)
        CAPTURE["dots"] = list(self.dots)
        return r

    # The layout the winning drawing was built from. `_render` ends by
    # drawing the winner again, and `_render_once` builds its layout
    # first thing, so the last one constructed is the winner's -- the
    # same reasoning that makes the canvas hook see the right pass.
    orig_init = sch._Layout.__init__

    def init(self, *a, **kw):
        orig_init(self, *a, **kw)
        LAYOUT["lay"] = self

    sch._Layout.__init__ = init
    sch._Canvas._flush_wires = flush
    sch._Canvas.raw = raw
    sch._Canvas._quality_hooked = True
    return sch


LAYOUT = {}


_VIEWBOX = re.compile(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')
_HOP = "A5 5 0 0"


def measure(desc):
    """The seven values for one description, plus its evidence."""
    sch = install()
    svg = sch.to_svg(desc)
    cap = dict(CAPTURE)
    m = _VIEWBOX.search(svg)
    w, h = float(m.group(3)), float(m.group(4))

    hor = [(a, b, y) for a, y, b, _y2 in cap["hor"]]        # x0, x1, y
    ver = [(x, a, b) for x, a, _x2, b in cap["ver"]]        # x, y0, y1
    # An element's axis segment is a line on the page too, and its body
    # is the part of it a wire may not cross.
    ehor, ever, bodies = [], [], []
    for x1, y1, x2, y2, half in cap["esegs"]:
        if abs(y1 - y2) < _EPS:
            ehor.append((x1, x2, y1))
        elif abs(x1 - x2) < _EPS:
            ever.append((x1, y1, y2))
        bodies.append(2.0 * half)

    # --- 1. crossings ------------------------------------------------
    crossings = svg.count(_HOP)

    # --- 2. bends ----------------------------------------------------
    # A corner: the end of a horizontal run meeting the end of a
    # vertical one at the same point.
    bends = 0
    for x0, x1, y in hor:
        for x, y0, y1 in ver:
            if (abs(x - x0) < 0.5 or abs(x - x1) < 0.5) \
                    and (abs(y - y0) < 0.5 or abs(y - y1) < 0.5):
                bends += 1

    # --- 3. joins near a corner --------------------------------------
    # Two line ends that land close to each other without meeting: the
    # reader sees a stub and a tee where the drawing means one corner
    # (#371). Ends of every line, wires and element segments alike.
    #
    # Two exclusions, both found by printing the evidence rather than
    # trusting the count. Without them TR5's Example 4-13 reports four
    # where it has two:
    #
    #  * **the two ends of one short run.** A 12px lead reported itself,
    #    which is a line, not a join.
    #  * **a pin.** The op-amp's two input leads end 29px apart on the
    #    body's own face -- that is `h/2`, the symbol's fixed pin
    #    spacing, and no rearrangement of the drawing can change it.
    #    #371 counted this one; it is the symbol, not the layout.
    #
    # And one more that is the same thought as the first: two lines that
    # **already meet** at a corner are not joining near a corner, they
    # are the corner. A 12px lead's far end is 12px from the corner its
    # near end makes, which is a short line and nothing else.
    keepout = list(cap["obstacles"]) + list(cap["blocks"])

    def _on_body(p):
        return any(x0 - 1 <= p[0] <= x1 + 1 and y0 - 1 <= p[1] <= y1 + 1
                   for x0, y0, x1, y1 in keepout)

    # The heights an op-amp's own three leads sit at: the two pins, at
    # `mid ± h/4`, and the output axis at `mid`. Since #375 both input
    # leads turn on one column, so their turns face each other across
    # `h/2` = 29px -- the symbol's fixed pin span, which no layout
    # choice can change. Two ends that are both at one op-amp's lead
    # heights are that symbol's geometry, not a corner the drawing
    # missed. Measured before believing it: of the 24 joins this
    # exclusion removes, **every one is 29.0 or 14.5px** and none is
    # any other distance.
    pin_ys = []
    for x0, y0, x1, y1 in cap["obstacles"]:
        mid, hh = (y0 + y1) / 2.0, y1 - y0
        pin_ys.append({mid - hh / 4.0, mid, mid + hh / 4.0})

    def _same_opamp_leads(a, b):
        if abs(a[0] - b[0]) > 0.5:
            return False
        return any(any(abs(a[1] - y) < 0.6 for y in ys)
                   and any(abs(b[1] - y) < 0.6 for y in ys)
                   for ys in pin_ys)

    ends = []                       # (point, id of the line it ends)
    line_ends = {}                  # line id -> its two endpoints
    for k, (x0, x1, y) in enumerate(hor + ehor):
        ends += [((x0, y), ("h", k)), ((x1, y), ("h", k))]
        line_ends[("h", k)] = ((x0, y), (x1, y))
    for k, (x, y0, y1) in enumerate(ver + ever):
        ends += [((x, y0), ("v", k)), ((x, y1), ("v", k))]
        line_ends[("v", k)] = ((x, y0), (x, y1))

    def _meet(ka, kb):
        return any(abs(p[0] - q[0]) < 0.5 and abs(p[1] - q[1]) < 0.5
                   for p in line_ends[ka] for q in line_ends[kb])

    near = []
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            (a, ka), (b, kb) = ends[i], ends[j]
            if ka == kb:
                continue                      # the same line's two ends
            # Only ends that share an axis. The defect is a lead teeing
            # into a column at the wrong height where the reader expects
            # one corner, so the two ends line up and miss -- every one
            # #371 measured is two ends on one x. Two ends merely *near*
            # each other diagonally are two different corners, and
            # counting them made narrowing a drawing look like a
            # regression when nothing had moved out of line.
            if abs(a[0] - b[0]) > 0.5 and abs(a[1] - b[1]) > 0.5:
                continue
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if not (_EPS < d < NEAR_CORNER):
                continue
            if _on_body(a) and _on_body(b):
                continue                      # two pins on one face
            if _meet(ka, kb):
                continue                      # they already share a corner
            if _same_opamp_leads(a, b):
                continue                      # the symbol's pin spacing
            near.append((round(d, 1), a, b))
    # One pair per place, not one per pair of coincident ends.
    seen, near_u = set(), []
    for d, a, b in sorted(near):
        key = (round(min(a[0], b[0])), round(min(a[1], b[1])),
               round(max(a[0], b[0])), round(max(a[1], b[1])))
        if key in seen:
            continue
        seen.add(key)
        near_u.append((d, a, b))

    # --- 4. dots -----------------------------------------------------
    # A dot earns its place when three or more lines actually meet
    # there. Its degree counts a line ending at the point as one and a
    # line passing through it as two.
    dots = []
    seen_d = set()
    for x, y in cap["dots"]:
        key = (round(x), round(y))
        if key in seen_d:
            continue
        seen_d.add(key)
        deg = 0
        for x0, x1, yy in hor + ehor:
            if abs(yy - y) > 0.5 or x < x0 - 0.5 or x > x1 + 0.5:
                continue
            deg += 1 if (abs(x - x0) < 0.5 or abs(x - x1) < 0.5) else 2
        for xx, y0, y1 in ver + ever:
            if abs(xx - x) > 0.5 or y < y0 - 0.5 or y > y1 + 0.5:
                continue
            deg += 1 if (abs(y - y0) < 0.5 or abs(y - y1) < 0.5) else 2
        dots.append((x, y, deg))
    # A *junction* dot short of three lines is the defect. A dot with no
    # line on it at all is not a junction at all: a coupling dot on a
    # mutual inductance and a transformer's polarity dots are the same
    # shape saying a different thing, and they are drawn inside the
    # symbol's own group. Counting them made 24 drawings -- every one in
    # Lesson 10, Lesson 13 or the monograph -- report a stray dot for
    # having a transformer in them, which is a metric counting something
    # other than its name.
    stray_dots = [d for d in dots if 1 <= d[2] < 3]

    # --- 5. figure size against element size -------------------------
    # Roberto's rule 5 as the drawing shows it: how much bare lead each
    # element is stretched over. A source with a 30px body drawn across
    # a 202px band is 172px of bare wire wearing a symbol.
    slack = []
    for (x1, y1, x2, y2, half), body in zip(cap["esegs"], bodies):
        span = math.hypot(x2 - x1, y2 - y1)
        if body > 0:
            slack.append((round(span - body, 1), round(span, 1), body))
    n_elem = max(1, len(slack))
    total_slack = sum(s[0] for s in slack)

    # --- 6. alignment ------------------------------------------------
    # Elements share rows and columns, or they do not. Counted as the
    # number of distinct axes an element's *body centre* sits on,
    # against the number of elements that could share one.
    rows = {round((y1 + y2) / 2.0) for x1, y1, x2, y2, half in cap["esegs"]
            if abs(y1 - y2) < _EPS and half > 0}
    cols = {round((x1 + x2) / 2.0) for x1, y1, x2, y2, half in cap["esegs"]
            if abs(x1 - x2) < _EPS and half > 0}
    n_h = sum(1 for s in cap["esegs"] if abs(s[1] - s[3]) < _EPS and s[4] > 0)
    n_v = sum(1 for s in cap["esegs"] if abs(s[0] - s[2]) < _EPS and s[4] > 0)

    # --- 7. lines that run together ----------------------------------
    # Two parallel lines overlapping along their length and closer than
    # CROWD_SEP: the pair Roberto saw in Practice Problem 5.9 ran 3px
    # apart for 61px. Weighted by how long they run together and how
    # close, so a long near pair costs more than a short one.
    crowd = []

    def _pairs(lines, vertical):
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                a, b = lines[i], lines[j]
                if vertical:
                    sep = abs(a[0] - b[0])
                    a0, a1, b0, b1 = a[1], a[2], b[1], b[2]
                    at, bt = a[0], b[0]
                else:
                    sep = abs(a[2] - b[2])
                    a0, a1, b0, b1 = a[0], a[1], b[0], b[1]
                    at, bt = a[2], b[2]
                if sep < 0.5 or sep >= CROWD_SEP:
                    continue
                ov = min(a1, b1) - max(a0, b0)
                if ov <= 0.5:
                    continue
                crowd.append((round(sep, 1), round(ov, 1),
                              "v" if vertical else "h", at, bt,
                              round(max(a0, b0), 1)))

    _pairs(ver + ever, True)
    _pairs(hor + ehor, False)

    return {
        "w": w, "h": h, "area": w * h,
        "n_elem": n_elem,
        "crossings": crossings,
        "bends": bends,
        "wires": len(hor) + len(ver),
        "near_corner": len(near_u),
        "near_corner_detail": near_u,
        "dots": len(dots),
        "stray_dots": len(stray_dots),
        "stray_dot_detail": stray_dots,
        "slack_total": round(total_slack, 1),
        "slack_per_elem": round(total_slack / n_elem, 1),
        "slack_max": round(max([s[0] for s in slack], default=0.0), 1),
        "slack_detail": sorted(slack, reverse=True)[:5],
        "area_per_elem": round(w * h / n_elem),
        "rows": len(rows), "n_h": n_h,
        "cols": len(cols), "n_v": n_v,
        "crowd": len(crowd),
        "crowd_worst": min([c[0] for c in crowd], default=None),
        "crowd_detail": sorted(crowd)[:5],
        "svg": svg,
    }


if __name__ == "__main__":
    import sys
    want = sys.argv[1] if len(sys.argv) > 1 else None
    for book, i, name, desc in common.entries():
        if want and want.lower() not in ("%s %s" % (book, name)).lower():
            continue
        q = measure(desc)
        print("%s [%d] %s" % (book, i, name))
        print("   %.0fx%.0f  elems=%d  cross=%d bends=%d wires=%d"
              % (q["w"], q["h"], q["n_elem"], q["crossings"], q["bends"],
                 q["wires"]))
        print("   near_corner=%d %s" % (q["near_corner"],
                                        q["near_corner_detail"][:3]))
        print("   dots=%d stray=%d  slack tot=%.0f max=%.0f  %s"
              % (q["dots"], q["stray_dots"], q["slack_total"],
                 q["slack_max"], q["slack_detail"][:3]))
        print("   rows=%d/%d cols=%d/%d  crowd=%d worst=%s %s"
              % (q["rows"], q["n_h"], q["cols"], q["n_v"], q["crowd"],
                 q["crowd_worst"], q["crowd_detail"][:2]))
