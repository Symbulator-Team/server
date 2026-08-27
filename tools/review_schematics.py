"""Render every circuit in ../examples/ as a schematic and check the lot.

The review harness behind the Aug 2026 schematic rework: every entry of
every .cir book is drawn with symbulator.schematic.to_svg and written
into an HTML gallery (one page per book, plus a denser drawings-only
grid page), and each drawing is checked for the things a reader would
call wrong:

  * an exception while drawing;
  * two labels overlapping (estimated from text metrics);
  * a wire crossing an element body, or entering an op-amp triangle
    anywhere but its three pins -- measured by instrumenting the
    canvas, not by parsing the SVG back;
  * an unusual number of crossing hops (a layout smell, not a bug);
  * an extreme drawing size.

The gallery lands in a temp folder by default (pass a directory as the
first argument to choose); report.txt inside it lists every finding,
worst first, and the index page links each one. A clean run ends
"failed=0 with_issues=0" -- that is the state the rework left all 322
tutorial circuits in, and the bar any schematic change should keep.

    py review_schematics.py
    py review_schematics.py C:\\somewhere\\gallery

Serve the output folder with any static server to browse it, e.g.
    py -m http.server 8741 --directory <gallery>

Imports the solver from a sibling checkout (../../solver) when one
exists, so it reviews the working tree rather than the installed
package; otherwise whatever `import symbulator` finds.
"""

import html
import os
import re
import sys
import tempfile
import traceback

TOOLS = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(TOOLS)
SOLVER = os.path.join(os.path.dirname(os.path.dirname(SERVER)), "solver")
if os.path.isdir(os.path.join(SOLVER, "symbulator")):
    sys.path.insert(0, SOLVER)
sys.path.insert(0, SERVER)

from symbulator.schematic import to_svg          # noqa: E402
import symbulator.schematic as sch               # noqa: E402
from circuitbook import parse_book               # noqa: E402

EXAMPLES = os.path.join(SERVER, "examples")
OUT = (sys.argv[1] if len(sys.argv) > 1
       else os.path.join(tempfile.gettempdir(), "symbulator_schematics"))

# --- instrumentation: count wires through bodies / triangles ---------
# The canvas keeps element segments (with their body half-lengths) and
# op-amp triangle boxes precisely so a harness can prove no wire
# violates them; the patched flush below does the proving.
ANALYSIS = {"bad": 0}
_orig_flush = sch._Canvas._flush_wires


def _patched_flush(self):
    bad = 0
    hor = [w for w in self.wires if abs(w[1] - w[3]) < 0.01]
    ver = [w for w in self.wires if abs(w[0] - w[2]) < 0.01]
    for x1, y, x2, _y in hor:
        for sx1, sy1, sx2, sy2, half in self.esegs:
            if abs(sx1 - sx2) > 0.01 or half <= 0:
                continue
            mid = (sy1 + sy2) / 2.0
            if x1 + 0.5 < sx1 < x2 - 0.5 and sy1 + 0.5 < y < sy2 - 0.5 \
                    and abs(y - mid) < half + 2:
                bad += 1
    for x, y1, _x, y2 in ver:
        for sx1, sy1, sx2, sy2, half in self.esegs:
            if abs(sy1 - sy2) > 0.01 or half <= 0:
                continue
            mid = (sx1 + sx2) / 2.0
            if y1 + 0.5 < sy1 < y2 - 0.5 and sx1 + 0.5 < x < sx2 - 0.5 \
                    and abs(x - mid) < half + 2:
                bad += 1
    # Wires entering (or grazing, within 4px of) an op-amp triangle,
    # except the pin connections on its faces and the output wire
    # rising straight from the tip corner.
    M = 4.0
    for ox0, oy0, ox1, oy1 in self.obstacles:
        bx0, by0, bx1, by1 = ox0 - M, oy0 - M, ox1 + M, oy1 + M
        for x1, y1, x2, y2 in self.wires:
            horiz = abs(y1 - y2) < 0.01
            if horiz:
                if not (by0 < y1 < by1 and x1 < bx1 and x2 > bx0):
                    continue
                if abs(x2 - ox0) < 1 or abs(x1 - ox1) < 1:
                    continue
                if abs(x1 - ox0) < 1 or abs(x2 - ox1) < 1:
                    continue
                bad += 1
            else:
                if bx0 < x1 < bx1 and y1 < by1 and y2 > by0:
                    tipy = (oy0 + oy1) / 2.0
                    if abs(x1 - ox1) < 1 and abs(max(y1, y2) - tipy) < 1:
                        continue
                    bad += 1
    ANALYSIS["bad"] = bad
    _orig_flush(self)


sch._Canvas._flush_wires = _patched_flush

# --- label-overlap estimation ---------------------------------------
TEXT_RE = re.compile(
    r'<text[^>]*x="([-\d.]+)" y="([-\d.]+)" text-anchor="(\w+)">([^<]*)</text>')
VIEWBOX_RE = re.compile(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')
CHAR_W = 7.3   # rough advance width for the 13px UI font
TEXT_H = 13.0


def text_boxes(svg):
    boxes = []
    for m in TEXT_RE.finditer(svg):
        x, y, anchor, s = (float(m.group(1)), float(m.group(2)),
                           m.group(3), m.group(4))
        w = len(s) * CHAR_W
        if anchor == "middle":
            x0 = x - w / 2
        elif anchor == "end":
            x0 = x - w
        else:
            x0 = x
        boxes.append((x0, y - TEXT_H, x0 + w, y + 2, s))
    return boxes


def overlap_count(svg):
    boxes = text_boxes(svg)
    n, pairs = 0, []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[4] == "" or b[4] == "":
                continue
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 2 and oy > 2:
                n += 1
                pairs.append((a[4], b[4]))
    return n, pairs


def main():
    os.makedirs(OUT, exist_ok=True)
    books = sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".cir"))
    index_rows = []
    report = []
    all_issues = []   # (score, book, name, anchor, issues)
    total = failed = 0

    for book in books:
        with open(os.path.join(EXAMPLES, book), encoding="utf-8") as f:
            circuits, warnings, title = parse_book(f.read())
        page = ['<!doctype html><meta charset="utf-8">',
                '<title>%s</title>' % html.escape(book),
                '<style>body{font:12px system-ui;margin:10px;'
                'background:#fff;color:#111}'
                '.entry{border-top:2px solid #bbb;padding:4px 0;'
                'display:flex;gap:10px}'
                'pre{background:#f4f4f4;padding:4px;font:10px monospace;'
                'min-width:170px;white-space:pre-wrap;max-width:240px;'
                'margin:2px 0}'
                'h2{margin:2px 0;font-size:13px}'
                '.issue{color:#b00;font-weight:bold}'
                'svg{border:1px dashed #ddd;max-width:100%;zoom:.8}</style>',
                '<h1>%s — %s</h1>' % (html.escape(book), html.escape(title))]
        grid = ['<!doctype html><meta charset="utf-8">',
                '<title>grid %s</title>' % html.escape(book),
                '<style>body{font:11px system-ui;margin:6px;'
                'background:#fff;color:#111}'
                '.wrap{display:flex;flex-wrap:wrap;gap:6px;'
                'align-items:flex-start}'
                '.card{border:1px solid #ccc;padding:2px}'
                '.card p{margin:0;font-weight:bold;color:#06c}'
                'svg{zoom:.55;display:block}</style>',
                '<div class="wrap">']
        for idx, c in enumerate(circuits):
            total += 1
            name, desc, anchor = c["name"], c["desc"], "c%d" % idx
            issues = []
            try:
                svg = to_svg(desc)
            except Exception as ex:
                failed += 1
                svg = None
                issues.append("EXCEPTION: %s" % ex)
                report.append("FAIL %s [%s]: %s" % (book, name, ex))
                report.append(traceback.format_exc(limit=3))
            if svg:
                m = VIEWBOX_RE.search(svg)
                w, h = float(m.group(3)), float(m.group(4))
                novl, pairs = overlap_count(svg)
                nbad = ANALYSIS["bad"]
                nhops = svg.count("A5 5 0 0")
                if novl:
                    issues.append("%d label overlaps: %s" % (
                        novl, "; ".join("%r/%r" % p for p in pairs[:6])))
                if nbad:
                    issues.append("%d wire-through-body" % nbad)
                if nhops > 3:
                    issues.append("%d hops" % nhops)
                if w > 1600:
                    issues.append("very wide: %.0f px" % w)
                if h > 900:
                    issues.append("very tall: %.0f px" % h)
                score = (novl * 10 + nbad * 40 + max(nhops - 3, 0) * 3
                         + (w > 1600) * 5 + (h > 900) * 5)
            else:
                score = 1000
            if issues:
                all_issues.append((score, book, name, anchor, issues))
            page.append('<div class="entry" id="%s"><div><h2>%s</h2>'
                        '<pre>%s</pre>%s</div><div>%s</div></div>' % (
                            anchor, html.escape(name), html.escape(desc),
                            "".join('<div class="issue">%s</div>'
                                    % html.escape(i) for i in issues),
                            svg or '<p class="issue">render failed</p>'))
            grid.append('<div class="card"><p>#%d %s</p>%s</div>' %
                        (idx, html.escape(name),
                         svg or "<p>FAIL</p>"))
        stem = book.replace(".cir", ".html")
        with open(os.path.join(OUT, stem), "w", encoding="utf-8") as f:
            f.write("\n".join(page))
        grid.append('</div>')
        with open(os.path.join(OUT, "grid_" + stem), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(grid))
        index_rows.append((book, len(circuits)))

    all_issues.sort(reverse=True)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><meta charset="utf-8">'
                '<title>Schematic gallery</title>'
                '<style>body{font:14px system-ui;margin:20px}'
                'td,th{padding:2px 10px;text-align:left}</style>'
                '<h1>Schematic gallery</h1><ul>')
        for book, n in index_rows:
            stem = book.replace(".cir", ".html")
            f.write('<li><a href="%s">%s</a> (%d) — '
                    '<a href="grid_%s">grid</a></li>' % (stem, book, n, stem))
        f.write('</ul><h2>Worst first</h2><table><tr><th>score</th>'
                '<th>book</th><th>circuit</th><th>issues</th></tr>')
        for score, book, name, anchor, issues in all_issues:
            f.write('<tr><td>%d</td><td><a href="%s#%s">%s</a></td>'
                    '<td>%s</td><td>%s</td></tr>' % (
                        score, book.replace(".cir", ".html"), anchor, book,
                        html.escape(name),
                        html.escape("; ".join(issues))))
        f.write('</table>')

    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
        f.write("total=%d failed=%d with_issues=%d\n\n" %
                (total, failed, len(all_issues)))
        for score, book, name, anchor, issues in all_issues:
            f.write("[%4d] %s | %s\n        %s\n" %
                    (score, book, name, " | ".join(issues)))
        f.write("\n\n--- failures ---\n")
        f.write("\n".join(report))
    print("total=%d failed=%d with_issues=%d -> %s" %
          (total, failed, len(all_issues), OUT))


if __name__ == "__main__":
    main()
