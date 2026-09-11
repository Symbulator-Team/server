"""Mock-ups: the rightmost grounded resistor laid along the ground line.

Roberto, 11 Sep 2026: *"life would be easier if the right-most resistor
was put horizontally along the ground line instead of vertically at the
right edge of the figure. Have you tried that? That would save a few
bends."*

Two readings, drawn rather than argued about. Built from the drawer's
own `_Canvas`, `_draw_element` and `_ground_symbol`, so the symbols, the
label placement, the junction dots and the wire merging are the real
ones -- only the coordinates are chosen by hand. The bend and wire
counts printed underneath come from `schematic._cost`, the same
function that prices every drawing in the book.

TR5's Example 4-13 is the subject, at its real geometry:

    e,1,0,vs : r1,1,2,r1 : r2,2,0,r2 : o,2,3,o : r3,o,3,r3 : r4,3,0,r4
"""
import html
import os
import sys

import common                                            # noqa: F401
from symbulator import schematic as sch
from symbulator.elements import parse_circuit

DESC = ("e,1,0,vs\nr1,1,2,r1\nr2,2,0,r2\no,2,3,o\n"
        "r3,o,3,r3\nr4,3,0,r4")

# The real drawing's geometry, read off `probe.py`.
X1, X_R2, X2, X_O, X3 = 58.0, 152.8, 247.6, 355.8, 545.4
Y_ROW, Y_RAIL, Y_R1 = 146.0, 302.8, 58.0
Y_PLUS, Y_MINUS = 131.5, 160.5          # the op-amp's two pins
Y_UNDER = 276.8
TX, TW = 276.6, 50.2                    # triangle left edge, width


def shell(cv):
    cv.flush()
    x0, y0 = cv.x0 - 26, cv.y0 - 26
    w, h = (cv.x1 - cv.x0) + 52, (cv.y1 - cv.y0) + 52
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="{0:g} {1:g} {2:g} {3:g}" width="{2:g}" height="{3:g}" '
        'fill="none" stroke="currentColor" stroke-width="1.7" '
        'stroke-linecap="round" stroke-linejoin="round" '
        'class="symbulator-schematic">'
        '<style>.symbulator-schematic .lbl{{font:13px/1 ui-sans-serif,'
        'system-ui,sans-serif;fill:currentColor;stroke:none}}'
        '.symbulator-schematic .sub{{font-size:{5:g}em}}</style>'
        '{4}</svg>'
    ).format(x0, y0, w, h, "".join(cv.parts), sch.SUB_SCALE)


def opamp(cv, mid):
    """The triangle, its pins and its name -- the same primitives
    `_draw_opamp` uses, at coordinates chosen here."""
    h = sch.OP_H
    cv.raw('<path d="M{0:g} {1:g} L{0:g} {2:g} L{3:g} {4:g} Z" '
           'fill="none"/>'.format(TX, mid - h / 2, mid + h / 2, TX + TW, mid),
           (TX, mid - h / 2), (TX + TW, mid + h / 2))
    cv.obstacle(TX, mid - h / 2, TX + TW, mid + h / 2)
    band = h / sch.OP_INK_BANDS
    for k in range(sch.OP_INK_BANDS):
        ya, yb = mid - h / 2 + k * band, mid - h / 2 + (k + 1) * band
        near = min(abs(ya - mid), abs(yb - mid))
        cv.ink(TX, ya, TX + TW * (1.0 - 2.0 * near / h), yb)
    sch._sign_mark(cv, TX + 13, mid - h / 4, True)
    sch._sign_mark(cv, TX + 13, mid + h / 4, False)
    nm = sch._name_runs("O")
    x_name = TX + TW / 2
    edge_x = max(TX, x_name - sch._runs_width(nm) / 2.0)
    y_slope = (mid - h / 2.0 + (edge_x - TX) / TW * (h / 2.0)
               - h / sch.OP_INK_BANDS)
    cv.runs(x_name, y_slope - sch.GAP - sch._name_below(), nm)


def build(variant):
    els = {e.name: e for e in parse_circuit(DESC, expand_si=False)}
    cv = sch._Canvas()
    D = sch._draw_element

    # --- the parts every version shares -------------------------------
    D(cv, els["r1"], X1, Y_R1, X2, Y_R1)            # r1, lifted row
    cv.wire(X1, Y_R1, X1, Y_ROW)
    cv.wire(X2, Y_R1, X2, Y_PLUS)
    D(cv, els["e"], X1, Y_RAIL, X1, Y_ROW)          # the source
    D(cv, els["r2"], X_R2, Y_PLUS, X_R2, Y_RAIL)    # r2, to the rail
    cv.wire(X_R2, Y_PLUS, TX, Y_PLUS)               # #377's straight line
    opamp(cv, Y_ROW)
    cv.wire(TX, Y_MINUS, X2, Y_MINUS)               # the inverting lead
    cv.wire(TX + TW, Y_ROW, X_O, Y_ROW)             # the output

    if variant == "now":
        D(cv, els["r3"], X_O, Y_ROW, X3, Y_ROW)
        D(cv, els["r4"], X3, Y_ROW, X3, Y_RAIL)     # vertical, right edge
        cv.wire(X2, Y_MINUS, X2, Y_UNDER)
        x_rise = (X_O + X3) / 2.0 + (X3 - X_O) / 4.0
        cv.wire(X2, Y_UNDER, x_rise, Y_UNDER)
        cv.wire(x_rise, Y_UNDER, x_rise, Y_ROW)
        cv.dot(x_rise, Y_ROW)
        cv.wire(X1, Y_RAIL, X3, Y_RAIL)
        rail_sym = X1
        names = [("1", X1), ("2", X2), ("o", X_O), ("3", X3)]

    elif variant == "A":
        # Reading A: R4 lies in the rail at its right-hand end, and node
        # 3 keeps the right edge -- it drops to the rail and the
        # resistor runs back along it. The figure loses the tall right
        # edge and gets shorter; the bend count is unchanged.
        x_end = X3 - 40.0
        D(cv, els["r3"], X_O, Y_ROW, x_end, Y_ROW)
        cv.wire(x_end, Y_ROW, x_end, Y_RAIL)
        D(cv, els["r4"], x_end, Y_RAIL, x_end - 150.0, Y_RAIL)
        cv.wire(X1, Y_RAIL, x_end - 150.0, Y_RAIL)
        cv.wire(X2, Y_MINUS, X2, Y_UNDER)
        x_rise = x_end - 60.0
        cv.wire(X2, Y_UNDER, x_rise, Y_UNDER)
        cv.wire(x_rise, Y_UNDER, x_rise, Y_ROW)
        cv.dot(x_rise, Y_ROW)
        rail_sym = X1
        names = [("1", X1), ("2", X2), ("o", X_O), ("3", x_end)]

    else:
        # Reading B: the same, but node 3 is the resistor's **left**
        # end, so the node reaches down beside the op-amp instead of at
        # the far right. The inverting return then never climbs back to
        # the node row -- it runs along under the body and turns up a
        # little way onto node 3's own drop.
        x_node3 = X_O + 150.0
        D(cv, els["r3"], X_O, Y_ROW, x_node3, Y_ROW)
        cv.wire(x_node3, Y_ROW, x_node3, Y_RAIL)
        D(cv, els["r4"], x_node3, Y_RAIL, x_node3 + 150.0, Y_RAIL)
        cv.wire(x_node3 + 150.0, Y_RAIL, x_node3 + 190.0, Y_RAIL)
        cv.wire(X1, Y_RAIL, x_node3, Y_RAIL)
        cv.wire(X2, Y_MINUS, X2, Y_UNDER)
        cv.wire(X2, Y_UNDER, x_node3, Y_UNDER)      # straight onto the drop
        cv.dot(x_node3, Y_UNDER)
        rail_sym = X1
        names = [("1", X1), ("2", X2), ("o", X_O), ("3", x_node3)]

    sch._ground_symbol(cv, rail_sym, Y_RAIL)
    for n, x in names:
        y = Y_PLUS if n == "2" else Y_ROW
        cv.text(x + 6, y - sch._HALF - sch.GAP - sch.LABEL_DESCENT, n, "start")
    return shell(cv)


CSS = """
:root{--bg:#faf9f7;--fg:#1a1a1a;--mut:#6b6b6b;--line:#d8d5d0;--card:#fff;
--accent:#0b6ea8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,sans-serif}
header{padding:20px 24px 14px;border-bottom:1px solid var(--line);
background:var(--card)}
h1{margin:0 0 6px;font-size:18px}
.sub{color:var(--mut);font-size:13px;max-width:80ch}
main{padding:16px 24px 50px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
margin:0 0 16px;overflow:hidden}
.head{padding:9px 14px;border-bottom:1px solid var(--line);font-weight:650}
.head em{font-weight:400;font-style:normal;color:var(--mut)}
.body{padding:10px 14px 14px}
.draw{overflow-x:auto}.draw svg{max-width:100%;height:auto;color:var(--fg)}
.nums{font:11.5px/1.6 ui-monospace,Menlo,monospace;color:var(--mut);
margin-top:8px}
.note{font-size:13px;color:var(--fg);margin:0 0 8px;max-width:82ch}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#16181c;--fg:#e9e7e3;--mut:#9a978f;--line:#33363c;--card:#1e2126;
--accent:#5cb3e8}}
"""

NOTES = [
    ("now", "As it is drawn today (#378)",
     "R4 vertical at the right edge. The inverting return runs under the "
     "body and turns up onto R3&rsquo;s lead."),
    ("A", "Reading A &mdash; R4 in the rail, node 3 still at the right",
     "Node 3 drops to the rail and R4 runs back along it. The tall right "
     "edge goes; the return still has to climb to the node row."),
    ("B", "Reading B &mdash; R4 in the rail, node 3 at its near end",
     "Node 3&rsquo;s drop comes down beside the op-amp, so the return "
     "never climbs back at all &mdash; it runs under the body and tees "
     "straight onto the drop."),
]


def main(out):
    cards = []
    for key, title, note in NOTES:
        svg = build(key)
        c, b, w = sch._cost(svg)
        import re
        m = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([-\d.]+) ([-\d.]+)"', svg)
        cards.append(
            '<section class="card"><div class="head">%s</div>'
            '<div class="body"><p class="note">%s</p><div class="draw">%s</div>'
            '<div class="nums">%s &times; %s &nbsp;&middot;&nbsp; '
            'crossings %d &nbsp;&middot;&nbsp; <b>bends %d</b> '
            '&nbsp;&middot;&nbsp; wires %d</div></div></section>'
            % (title, note, svg, m.group(1), m.group(2), c, b, w))
        print("%-4s  %6s x %-6s  crossings=%d bends=%d wires=%d"
              % (key, m.group(1), m.group(2), c, b, w))
    page = ('<!doctype html><meta charset="utf-8">'
            '<title>R4 along the ground line</title><style>%s</style>'
            '<header><h1>The rightmost resistor along the ground line '
            '&mdash; two readings</h1><div class="sub">Mock-ups, not the '
            'drawer: the coordinates are chosen by hand, but the symbols, '
            'labels, junction dots and wire merging are the real ones, and '
            'the counts underneath come from <code>_cost</code>, the same '
            'function that prices every drawing in the book. The first card '
            'is a mock of the drawing as it stands, and it prices identically '
            'to the real one &mdash; <code>(0, 4, 20)</code> &mdash; so the '
            'three are comparable.<br><br><b>Measured: neither reading saves '
            'a bend.</b> All three sit at four corners. A is 54px narrower, '
            'B is 123px wider, and both add one wire. B moves the corner '
            'rather than removing it: the return stops climbing to the node '
            'row, but the rail now turns into node 3&rsquo;s drop instead. '
            'If you are counting something I have not drawn here, say which '
            'line you mean and I will draw that.</div>'
            '</header><main>%s</main>' % (CSS, "".join(cards)))
    with open(out, "wb") as f:
        f.write(page.encode("utf-8"))
    print("\n%s (%.0f KB)" % (out, os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mock_ground.html")
