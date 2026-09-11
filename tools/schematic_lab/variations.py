"""The same circuits at several settings of the three new constants.

`LEAD_MIN`, `H_CLEAR` and `LABEL_APART` decide how tight a drawing gets.
None of them is derived -- each is a look-and-feel number with a
measured range -- so the choice is Roberto's, and the way he makes those
is by looking at rendered variations side by side.

Column A is 0.6.4 as shipped. The rest are progressively tighter.
"""
import html
import importlib
import re
import sys

import common

VIEWBOX = re.compile(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')

# (label, lead_min, h_clear, label_apart) -- None means "as shipped".
SETTINGS = [
    ("as shipped<br><small>0.6.4</small>", None, None, None),
    ("roomy<br><small>lead 44 &middot; gap 28 &middot; labels 26</small>",
     44.0, 28.0, 26.0),
    ("proposed<br><small>lead 34 &middot; gap 20 &middot; labels 18</small>",
     34.0, 20.0, 18.0),
    ("tight<br><small>lead 26 &middot; gap 14 &middot; labels 12</small>",
     26.0, 14.0, 12.0),
]

PICKS = [
    "Bo2's Drill Exercise 3.2",
    "TR5's Example 4-13 (Non-Inverting, in one)",
    "Bo2's Drill Exercise 3.3 (Difference)",
    "Bo2's Example 3.3 (Cascade)",
    "B11's Example 7.10",
    "AS7's Example 12.11 (wye-delta with line impedances)",
    "The two-stage amplifier of 1999",
    "AS2's Practice Problem 5.8 (Instrumentation)",
]

CSS = """
:root{--bg:#faf9f7;--fg:#1a1a1a;--mut:#6b6b6b;--line:#d8d5d0;--card:#fff;
--accent:#0b6ea8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:22px 26px 16px;border-bottom:1px solid var(--line);
background:var(--card)}
h1{margin:0 0 6px;font-size:19px}
.sub{color:var(--mut);font-size:13px;max-width:76ch}
main{padding:18px 26px 60px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
margin:0 0 16px;overflow:hidden;content-visibility:auto;
contain-intrinsic-size:auto 380px}
.head{padding:9px 14px;border-bottom:1px solid var(--line);font-weight:650;
font-size:14px}
.head span{color:var(--mut);font-weight:400;font-size:12px;
font-variant:all-small-caps;letter-spacing:.04em;margin-left:8px}
.row{display:grid;grid-template-columns:repeat(4,1fr)}
.col{padding:9px 12px 14px;min-width:0}
.col+.col{border-left:1px solid var(--line)}
.tag{font-size:11px;color:var(--mut);font-variant:all-small-caps;
letter-spacing:.04em;margin-bottom:6px;min-height:2.6em}
.tag small{font-variant:none;letter-spacing:0;opacity:.8}
.dim{font:11px ui-monospace,Menlo,monospace;color:var(--mut);
margin-top:6px}
.draw{overflow-x:auto}
.draw svg{max-width:100%;height:auto;color:var(--fg)}
@media (max-width:1000px){.row{grid-template-columns:1fr 1fr}
.col+.col{border-left:0}.col:nth-child(n+3){border-top:1px solid var(--line)}}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#16181c;--fg:#e9e7e3;--mut:#9a978f;--line:#33363c;--card:#1e2126;
--accent:#5cb3e8}}
"""


def render(desc, lead, hclear, apart):
    from symbulator import schematic as sch
    if lead is None:
        sch.LEAD_MIN, sch.H_CLEAR, sch.LABEL_APART = 1e9, 1e9, 0.0
    else:
        sch.LEAD_MIN, sch.H_CLEAR, sch.LABEL_APART = lead, hclear, apart
    return sch.to_svg(desc)


def main(out):
    from symbulator import schematic as sch
    keep = (sch.LEAD_MIN, sch.H_CLEAR, sch.LABEL_APART)
    entries = {n: (b, d) for b, _i, n, d in common.entries()}
    cards = []
    for name in PICKS:
        if name not in entries:
            print("  (no entry called %r)" % name)
            continue
        book, desc = entries[name]
        cols = []
        for label, lead, hc, ap in SETTINGS:
            svg = render(desc, lead, hc, ap)
            m = VIEWBOX.search(svg)
            w, h = float(m.group(3)), float(m.group(4))
            cols.append('<div class="col"><div class="tag">%s</div>'
                        '<div class="draw">%s</div>'
                        '<div class="dim">%.0f &times; %.0f</div></div>'
                        % (label, svg, w, h))
        cards.append('<section class="card"><div class="head">%s'
                     '<span>%s</span></div><div class="row">%s</div>'
                     '</section>'
                     % (html.escape(name),
                        html.escape(book.replace(".cir", "")), "".join(cols)))
    sch.LEAD_MIN, sch.H_CLEAR, sch.LABEL_APART = keep
    page = ('<title>Relaxation settings</title><style>%s</style>'
            '<header><h1>How tight? &mdash; the three constants, side by '
            'side</h1><div class="sub">None of these three numbers is '
            'derived. Each is a look-and-feel choice with a measured range: '
            'below about 5px of lead the review harness goes red, and the '
            'book as shipped sits at 56px of lead and 45px between '
            'neighbouring labels. <b>Everything else in this work is '
            'measurement; this is taste, and it is yours.</b> Pick a column '
            'or name your own numbers.</div></header><main>%s</main>'
            % (CSS, "".join(cards)))
    with open(out, "wb") as f:
        f.write(page.encode("utf-8"))
    import os
    print("%s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "variations.html")
