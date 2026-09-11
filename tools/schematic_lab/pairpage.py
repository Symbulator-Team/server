"""A focused before/after page for a named handful of drawings.

`gallery.py` is the whole book; this is the two or three drawings under
discussion, from two snapshot directories, at full size.

    py pairpage.py <before-dir> <after-dir> out.html "name substring" ...
"""
import html
import json
import os
import re
import sys

VIEWBOX = re.compile(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')

CSS = """
:root{--bg:#faf9f7;--fg:#1a1a1a;--mut:#6b6b6b;--line:#d8d5d0;--card:#fff;
--accent:#0b6ea8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,sans-serif}
header{padding:20px 24px 14px;border-bottom:1px solid var(--line);
background:var(--card)}
h1{margin:0 0 6px;font-size:18px}
.sub{color:var(--mut);font-size:13px;max-width:78ch}
main{padding:16px 24px 50px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
margin:0 0 14px;overflow:hidden}
.head{padding:8px 13px;border-bottom:1px solid var(--line);font-weight:650}
.head span{color:var(--mut);font-weight:400;font-size:12px;
font-variant:all-small-caps;letter-spacing:.04em;margin-left:8px}
.row{display:grid;grid-template-columns:1fr 1fr}
.col{padding:8px 12px 12px;min-width:0}
.col+.col{border-left:1px solid var(--line)}
.tag{font-size:11px;color:var(--mut);font-variant:all-small-caps;
letter-spacing:.05em;margin-bottom:5px;display:flex;
justify-content:space-between}
.draw{overflow-x:auto}.draw svg{max-width:100%;height:auto;color:var(--fg)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#16181c;--fg:#e9e7e3;--mut:#9a978f;--line:#33363c;--card:#1e2126;
--accent:#5cb3e8}}
"""


def load(d):
    with open(os.path.join(d, "index.json"), "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def svg(d, stem):
    with open(os.path.join(d, stem + ".svg"), "rb") as f:
        return f.read().decode("utf-8")


def main(before, after, out, title, *wanted):
    idx = load(after)
    cards = []
    for r in idx:
        if wanted and not any(w.lower() in r["name"].lower() for w in wanted):
            continue
        a, b = svg(before, r["stem"]), svg(after, r["stem"])
        if a == b and wanted:
            pass
        panes = []
        for tag, s in (("before", a), ("after", b)):
            m = VIEWBOX.search(s)
            panes.append('<div class="col"><div class="tag"><span>%s</span>'
                         '<span>%.0f &times; %.0f</span></div>'
                         '<div class="draw">%s</div></div>'
                         % (tag, float(m.group(3)), float(m.group(4)), s))
        cards.append('<section class="card"><div class="head">%s'
                     '<span>%s</span></div><div class="row">%s</div>'
                     '</section>'
                     % (html.escape(r["name"]),
                        html.escape(r["book"].replace(".cir", "")),
                        "".join(panes)))
    page = ('<!doctype html><meta charset="utf-8"><title>%s</title>'
            '<style>%s</style><header><h1>%s</h1></header><main>%s</main>'
            % (html.escape(title), CSS, html.escape(title), "".join(cards)))
    with open(out, "wb") as f:
        f.write(page.encode("utf-8"))
    print("%s  (%d drawings, %.0f KB)"
          % (out, len(cards), os.path.getsize(out) / 1024))


if __name__ == "__main__":
    main(*sys.argv[1:])
