"""What equal op-amp legs would actually look like.

Roberto, 11 Sep 2026: *"I'd very much like both legs to be the same
length whenever there is no good reason for them to be different."*

There is a geometric catch, and it is the whole of the question. Both
input leads leave the body's left face and turn vertically at the far
end of their stub -- the upper one up to its node, the lower one down.
**Equal stubs put both turns on one column**, so the two verticals
become collinear with a 29px gap between them where the triangle's
mouth is. Whether that reads as clean symmetry or as one wire passing
behind the symbol is a judgement, not a measurement, so this renders
both and asks.

Three columns: as it is today, equal stubs, and equal stubs with the
lower lead's turn splayed 10px so the two verticals are near but not
collinear.

The `-30` is left alone where it has a job: a grounded input drops to
the rail on that column, and a captured source is *drawn* in the drop,
so either would land on the upper input's riser.
"""
import html
import re
import sys

import common
from symbulator import schematic as sch
from symbulator.elements import parse_circuit

VIEWBOX = re.compile(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')
OFFSET = [30.0]


def install():
    if getattr(sch, "_legsym_hooked", False):
        return
    src = sch._draw_opamp.__code__
    # Patch the constant by re-deriving x_p: the cleanest hook is to
    # wrap `_Canvas.wire` and move the lower lead, but that cannot see
    # which wire is which. So the experiment edits the source instead --
    # see `render_at`, which swaps the file. This function only marks
    # the module so the wrapper is not installed twice.
    sch._legsym_hooked = True
    return src


PICKS = [
    "AS2's Example 5.2",
    "AS2's Figure 5.16 (Non-Inverting Amplifier)",
    "TR5's Example 4-13 (Non-Inverting, in one)",
    "Bo2's Drill Exercise 3.3 (Difference)",
    "AS2's Example 5.9 (Cascade)",
    "Bo2's Drill Exercise 3.2",
]

CSS = """
:root{--bg:#faf9f7;--fg:#1a1a1a;--mut:#6b6b6b;--line:#d8d5d0;--card:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,sans-serif}
header{padding:20px 24px 14px;border-bottom:1px solid var(--line);
background:var(--card)}
h1{margin:0 0 6px;font-size:18px}
.sub{color:var(--mut);font-size:13px;max-width:76ch}
main{padding:16px 24px 50px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
margin:0 0 14px;overflow:hidden}
.head{padding:8px 13px;border-bottom:1px solid var(--line);font-weight:650}
.row{display:grid;grid-template-columns:repeat(3,1fr)}
.col{padding:8px 12px 12px;min-width:0}
.col+.col{border-left:1px solid var(--line)}
.tag{font-size:11px;color:var(--mut);font-variant:all-small-caps;
letter-spacing:.05em;margin-bottom:5px}
.draw{overflow-x:auto}.draw svg{max-width:100%;height:auto;color:var(--fg)}
.dim{font:11px ui-monospace,Menlo,monospace;color:var(--mut);margin-top:5px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#16181c;--fg:#e9e7e3;--mut:#9a978f;--line:#33363c;--card:#1e2126}}
"""


def main(out="legsymmetry.html"):
    import at_rev
    import os
    import subprocess
    target = at_rev.TARGET
    with open(target, "rb") as f:
        keep = f.read()
    # The offset is kept where it has a job -- a grounded input drops to
    # the rail on that column, and a captured source is *drawn* in the
    # drop, so either would land on the upper input's riser. Swapping
    # the bare constant instead pulls the source hard against the
    # triangle, which is a different (and worse) picture than the one
    # this page is asking about.
    keep_it = (b'x_in - (30 if (dn_node == "0" '
               b'or e.name in lay.op_src) else %d) - lane * 16')
    variants = [("as it is today<br><small>lower lead 30px past its "
                 "column</small>", b"x_in - 30 - lane * 16"),
                ("equal stubs<br><small>both turn on one column</small>",
                 keep_it % 0),
                ("equal, splayed 10px<br><small>near but not "
                 "collinear</small>", keep_it % 10)]
    entries = {n: d for _b, _i, n, d in common.entries()}
    cols = {}
    try:
        for label, repl in variants:
            body = keep.replace(b"x_in - 30 - lane * 16", repl)
            assert body != keep or repl == b"x_in - 30 - lane * 16"
            with open(target, "wb") as f:
                f.write(body)
            script = (
                "import sys, json\n"
                "sys.path.insert(0, %r)\n"
                "import common\n"
                "from symbulator import schematic as sch\n"
                "picks = %r\n"
                "out = {}\n"
                "for b, i, n, d in common.entries():\n"
                "    if n in picks:\n"
                "        out[n] = sch.to_svg(d)\n"
                "print(json.dumps(out))\n"
                % (os.path.dirname(os.path.abspath(__file__)), PICKS))
            p = subprocess.run([sys.executable, "-c", script],
                               capture_output=True,
                               cwd=os.path.dirname(os.path.abspath(__file__)))
            if p.returncode:
                raise SystemExit(p.stderr.decode("utf-8", "replace"))
            import json
            cols[label] = json.loads(p.stdout.decode("utf-8"))
    finally:
        with open(target, "wb") as f:
            f.write(keep)
        with open(target, "rb") as f:
            assert f.read() == keep, "RESTORE FAILED -- fix by hand"
        print("restored %s" % target)

    cards = []
    for name in PICKS:
        if name not in entries:
            continue
        panes = []
        for label, _repl in variants:
            svg = cols[label].get(name, "")
            m = VIEWBOX.search(svg)
            dim = "%.0f &times; %.0f" % (float(m.group(3)),
                                         float(m.group(4))) if m else ""
            panes.append('<div class="col"><div class="tag">%s</div>'
                         '<div class="draw">%s</div>'
                         '<div class="dim">%s</div></div>' % (label, svg, dim))
        cards.append('<section class="card"><div class="head">%s</div>'
                     '<div class="row">%s</div></section>'
                     % (html.escape(name), "".join(panes)))
    page = ('<!doctype html><meta charset="utf-8">'
            '<title>Op-amp leg symmetry</title><style>%s</style>'
            '<header><h1>Op-amp input legs &mdash; three ways</h1>'
            '<div class="sub">The two input leads leave the body and turn '
            'vertically at the end of their stub. <b>Equal stubs put both '
            'turns on the same column</b>, so the two verticals become '
            'collinear with the triangle&rsquo;s mouth between them. '
            'Middle column is that; right column splays the lower turn by '
            '10px so they are near but distinct. Grounded inputs and '
            'captured sources keep the old offset in every column &mdash; '
            'their drop needs its own line.</div></header><main>%s</main>'
            % (CSS, "".join(cards)))
    with open(out, "wb") as f:
        f.write(page.encode("utf-8"))
    print("%s (%.0f KB)" % (out, os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "legsymmetry.html")
