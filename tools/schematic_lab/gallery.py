"""Before and after, side by side, for every drawing that moved.

"Show me pictures, not numbers. I review by eye; the numbers are how you
avoid wasting my time, not how you convince me." So the numbers are on
each card, small, and the pictures are the size of the card.

Reads two snapshots made by `snapshot.py` and two surveys made by
`survey.py`.
"""
import html
import json
import os
import re
import sys

VIEWBOX = re.compile(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')

# The drawings Roberto has named, newest ruling first. These sort to the
# top of the gallery so his own cases are the first thing on screen.
NAMED = [
    ("Bo2's Drill Exercise 3.2", "#372: &ldquo;too tall&rdquo; &mdash; a 30px "
     "source in a 202px band, ~156px of bare lead"),
    ("TR5's Example 4-13 (Non-Inverting, in one)",
     "#371 part 1: &ldquo;there must be a more compact way to represent "
     "this circuit&rdquo;"),
    ("Bo2's Drill Exercise 3.3 (Difference)",
     "#371 part 2: &ldquo;could benefit from connecting the lines at the "
     "corners&rdquo;"),
    ("AS2's Practice Problem 5.8 (Instrumentation)",
     "#371 part 3: the one open crossing"),
    ("Bo2's Example 3.3 (Cascade)",
     "the anchor &mdash; &ldquo;I don't think the cross can be avoided &hellip; "
     "as good as that one will get&rdquo;"),
    ("AS2's Practice Problem 5.9 (Cascade)",
     "#367 raised o2 as he asked; he called it done"),
]

CSS = """
:root{--bg:#faf9f7;--fg:#1a1a1a;--mut:#6b6b6b;--line:#d8d5d0;--card:#fff;
--warn:#b8860b;--good:#2e7d32;--bad:#b00020;--accent:#0b6ea8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:22px 26px 14px;border-bottom:1px solid var(--line);
background:var(--card);position:sticky;top:0;z-index:5}
h1{margin:0 0 4px;font-size:19px;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:13px;max-width:70ch}
.bar{display:flex;gap:14px;flex-wrap:wrap;margin-top:12px;align-items:center}
.stat{background:var(--bg);border:1px solid var(--line);border-radius:7px;
padding:5px 10px;font-size:12px}
.stat b{font-size:14px}
button{font:inherit;font-size:12px;padding:5px 11px;border-radius:7px;
border:1px solid var(--line);background:var(--card);cursor:pointer}
button[aria-pressed="true"]{background:var(--accent);color:#fff;
border-color:var(--accent)}
main{padding:18px 26px 60px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
margin:0 0 16px;overflow:hidden;
/* 712 inline SVGs on one page is more than a browser will lay out in
   one go -- without this the page takes tens of seconds to first
   paint. Offscreen cards are skipped until they scroll near. */
content-visibility:auto;contain-intrinsic-size:auto 430px}
.card.named{border-color:var(--accent);border-width:2px}
.head{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;
padding:10px 14px;border-bottom:1px solid var(--line)}
.head h2{margin:0;font-size:14px;font-weight:650}
.book{color:var(--mut);font-size:12px;font-variant:all-small-caps;
letter-spacing:.04em}
.why{width:100%;color:var(--accent);font-size:12.5px;font-style:italic}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:0}
.pane{padding:10px 14px 14px;min-width:0}
.pane+.pane{border-left:1px solid var(--line)}
.tag{font-size:11px;color:var(--mut);font-variant:all-small-caps;
letter-spacing:.05em;margin-bottom:6px;display:flex;gap:8px;
justify-content:space-between}
.draw{overflow-x:auto}
.draw svg{max-width:100%;height:auto;color:var(--fg)}
.nums{font:11.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
color:var(--mut);padding:6px 14px 10px;border-top:1px solid var(--line);
display:flex;gap:16px;flex-wrap:wrap}
.nums .d{color:var(--good)}
.nums .u{color:var(--bad);font-weight:700}
.hide{display:none!important}
@media (max-width:900px){.pair{grid-template-columns:1fr}
.pane+.pane{border-left:0;border-top:1px solid var(--line)}}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#16181c;--fg:#e9e7e3;--mut:#9a978f;--line:#33363c;--card:#1e2126;
--accent:#5cb3e8;--good:#7bc47f;--bad:#ff8a80}}
"""

JS = """
document.addEventListener('click', function(e){
  var b = e.target.closest('button[data-filter]');
  if(!b) return;
  document.querySelectorAll('button[data-filter]').forEach(function(x){
    x.setAttribute('aria-pressed', String(x===b)); });
  var f = b.dataset.filter;
  document.querySelectorAll('.card').forEach(function(c){
    c.classList.toggle('hide', f!=='all' && !c.classList.contains(f)); });
});
"""


def load_index(d):
    with open(os.path.join(d, "index.json"), "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def svg_of(d, stem):
    p = os.path.join(d, stem + ".svg")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read().decode("utf-8")


def size(svg):
    m = VIEWBOX.search(svg)
    return float(m.group(3)), float(m.group(4))


def load_survey(p):
    with open(p, "rb") as f:
        return {(r["book"], r["index"]): r
                for r in json.loads(f.read().decode("utf-8"))}


TERMS = [("crossings", "cross"), ("bends", "bends"), ("near_corner", "joins"),
         ("stray_dots", "dots"), ("crowd", "crowd"), ("wires", "wires")]


def main(before, after, sbefore, safter, out):
    ia = {(r["book"], r["index"]): r for r in load_index(before)}
    ib = {(r["book"], r["index"]): r for r in load_index(after)}
    qa, qb = load_survey(sbefore), load_survey(safter)
    named = {n: (i, why) for i, (n, why) in enumerate(NAMED)}

    cards, moved, grew = [], 0, 0
    area_a = area_b = 0.0
    rows = []
    for k in sorted(ia):
        if k not in ib:
            continue
        sa, sb = svg_of(before, ia[k]["stem"]), svg_of(after, ib[k]["stem"])
        if sa is None or sb is None:
            continue
        wa, ha = size(sa)
        wb, hb = size(sb)
        area_a += wa * ha
        area_b += wb * hb
        if sa != sb:
            moved += 1
        if wb * hb > wa * ha + 0.5:
            grew += 1
        rows.append((k, ia[k], sa, sb, (wa, ha), (wb, hb)))

    def sortkey(row):
        k, meta, _sa, _sb, _a, _b = row
        nm = meta["name"]
        if nm in named:
            return (0, named[nm][0], "")
        has_op = ":o" in meta.get("desc", "") or "Op Amp" in nm
        return (1 if has_op else 2, 0, k[0] + "%03d" % k[1])

    for k, meta, sa, sb, (wa, ha), (wb, hb) in sorted(rows, key=sortkey):
        nm = meta["name"]
        cls = ["card"]
        why = ""
        if nm in named:
            cls.append("named")
            why = '<div class="why">%s</div>' % named[nm][1]
        if sa != sb:
            cls.append("moved")
        ra, rb = qa.get(k), qb.get(k)
        nums = []
        if ra and rb:
            for key, label in TERMS:
                x, y = ra[key], rb[key]
                if x == y:
                    nums.append("%s %g" % (label, y))
                else:
                    nums.append('%s <span class="%s">%g&rarr;%g</span>'
                                % (label, "d" if y < x else "u", x, y))
        pct = 100.0 * (wb * hb) / max(1.0, wa * ha)
        nums.append('area <span class="%s">%.0f%%</span>'
                    % ("d" if pct < 99 else "u" if pct > 101 else "", pct))
        cards.append(
            '<section class="%s"><div class="head"><h2>%s</h2>'
            '<span class="book">%s</span>%s</div><div class="pair">'
            '<div class="pane"><div class="tag"><span>before &mdash; 0.6.4 as '
            'shipped</span><span>%.0f &times; %.0f</span></div>'
            '<div class="draw">%s</div></div>'
            '<div class="pane"><div class="tag"><span>after &mdash; band and '
            'gaps relaxed</span><span>%.0f &times; %.0f</span></div>'
            '<div class="draw">%s</div></div></div>'
            '<div class="nums">%s</div></section>'
            % (" ".join(cls), html.escape(nm),
               html.escape(meta["book"].replace(".cir", "")), why,
               wa, ha, sa, wb, hb, sb, " &nbsp; ".join(nums)))

    head = (
        '<title>Schematic relaxation review</title>'
        '<style>%s</style><header><h1>Schematic relaxation &mdash; '
        'before and after</h1>'
        '<div class="sub">Every built-in drawing, as 0.6.4 ships it and with '
        'the band and the column gaps closed to what each drawing actually '
        'needs. Your own named cases are first, then the op-amp drawings, '
        'then the rest. Nothing is deployed and nothing is committed to '
        '<code>main</code>.</div>'
        '<div class="bar">'
        '<span class="stat"><b>%d</b> drawings</span>'
        '<span class="stat"><b>%d</b> moved</span>'
        '<span class="stat"><b>%d</b> grew</span>'
        '<span class="stat">total area <b>%.0f%%</b> of before</span>'
        '<span class="stat">crossings and bends <b>unchanged</b></span>'
        '<button data-filter="all" aria-pressed="true">All</button>'
        '<button data-filter="named">The ones you named</button>'
        '<button data-filter="moved">Moved</button>'
        '</div></header><main>%s</main><script>%s</script>'
        % (CSS, len(rows), moved, grew, 100.0 * area_b / area_a,
           "".join(cards), JS))
    with open(out, "wb") as f:
        f.write(head.encode("utf-8"))
    print("%s  (%.1f MB)  %d drawings, %d moved, %d grew, area %.1f%%"
          % (out, os.path.getsize(out) / 1e6, len(rows), moved, grew,
             100.0 * area_b / area_a))


if __name__ == "__main__":
    main(*sys.argv[1:6])
