"""#239: how wide each entry's picture should be drawn.

An entry's `image:` may carry a cap -- `<url> [400px]` (#235). This works
out what that cap should be, so the decision is computed rather than
eyeballed 299 times.

**The rule is not ours.** The documentation already solves this problem:
`build.py`'s `figure_size_mm()` (#153) renders every figure at the width
that puts *the lettering inside the scan* at the size of the body text,
using measurements from `Sym Docum/Documentation/tools/figure_sizes.json`
written by `measure_figures.py`. The app was the one surface that never
got it, which is why a simple divider and a dense op-amp network were
both stretched to the full card:

    cap = natural_width x body_text_px / text_px

Roberto's brief, 3 Sep 2026: *"examine the image, find the size of text
and symbols, and extrapolate from there"* and *"letters and symbols
should not look huge"*. That is the same rule, arrived at independently.

Measured before it was written: of the 299 links, only 6 pictures are
smaller than the card, so nothing was being blown up -- 200 were already
being *shrunk*. The complaint was never about scaling. It was that
`hk5s-figure-1-26-1.jpg` has 51px lettering, so at the card's 620px its
letters land at 36px against 16px body text. Capped at 278px they land
at 16px.

    py tools\\image_caps.py              # what would change
    py tools\\image_caps.py --sheet FILE # a contact sheet to look at
    py tools\\image_caps.py --write      # write the caps into the .cir files

Only entries whose cap is *narrower* than the card get one: a picture
already showing at or below its computed width needs no instruction, and
an absent cap keeps the file as clean as it is now.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent
EXAMPLES = SERVER / "examples"
DOCS = SERVER.parent.parent.parent / "Sym Docum" / "Documentation"
SIZES = DOCS / "tools" / "figure_sizes.json"

#: The app's body text, in px -- what the lettering inside a scan should
#: match. One number; move it and every cap moves together.
BODY_PX = 16.0

#: The Input File card's inner width on a desktop screen. A cap wider
#: than this would never bind, so it is not written.
CARD_PX = 620

#: `image: <url>` with the optional #235 cap.
LINE_RE = re.compile(r"^(?P<pre>image:\s*)(?P<url>\S+)"
                     r"(?:\s+\[(?P<cap>\d+)px\])?\s*$", re.I)
SECTION_RE = re.compile(r"^\[(?P<name>.+)\]\s*$")
BASE = "https://learn.symbulator.com/"


def measurements() -> dict:
    if not SIZES.is_file():
        raise SystemExit(
            f"image_caps.py: {SIZES} is missing. The lettering sizes are "
            "measured on the docs side by tools/measure_figures.py; this "
            "needs 'Sym Docum' beside 'Symbulator'.")
    return json.loads(SIZES.read_text(encoding="utf-8"))["measured"]


def cap_for(url: str, meas: dict):
    """(cap_px, natural_w, text_px) or None when it cannot be judged."""
    if not url.startswith(BASE + "assets/"):
        return None
    rel = url[len(BASE) + len("assets/"):]
    m = meas.get(rel)
    if not m or not m.get("text_px") or not m.get("w"):
        return None
    return (round(m["w"] * BODY_PX / m["text_px"]), m["w"], m["text_px"])


def scan(meas: dict):
    """Every image line, as (path, entry, url, current_cap, computed)."""
    out = []
    for path in sorted(EXAMPLES.glob("*.cir")):
        entry = "(before the first entry)"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            sm = SECTION_RE.match(line.strip())
            if sm:
                entry = sm.group("name").strip()
                continue
            m = LINE_RE.match(line)
            if not m:
                continue
            url = m.group("url")
            cur = int(m.group("cap")) if m.group("cap") else None
            out.append((path, entry, i, url, cur, cap_for(url, meas)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="write the caps into the .cir files")
    ap.add_argument("--sheet", metavar="FILE",
                    help="write a contact sheet for review")
    args = ap.parse_args()

    meas = measurements()
    rows = scan(meas)
    todo = [r for r in rows if r[5] and r[5][0] < CARD_PX and r[4] != r[5][0]]
    unjudged = [r for r in rows if not r[5]]

    print(f"{len(rows)} image links | {len(todo)} would gain or change a cap "
          f"| {len(rows) - len(todo) - len(unjudged)} left at full width "
          f"| {len(unjudged)} not measured")

    if args.sheet:
        write_sheet(args.sheet, rows, todo)
        print(f"contact sheet: {args.sheet}")

    if args.write:
        by_file: dict = {}
        for path, entry, i, url, cur, comp in todo:
            by_file.setdefault(path, []).append((i, url, comp[0]))
        for path, edits in by_file.items():
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            for i, url, cap in edits:
                nl = "\n" if lines[i].endswith("\n") else ""
                lines[i] = f"image: {url} [{cap}px]{nl}"
            path.write_text("".join(lines), encoding="utf-8")
        print(f"wrote caps into {len(by_file)} file(s)")
    return 0


def write_sheet(dest: str, rows, todo):
    """A page showing each picture as it is drawn now beside the cap."""
    changed = {(str(p), i) for p, _e, i, _u, _c, _m in todo}
    cards = []
    for path, entry, i, url, cur, comp in rows:
        if (str(path), i) not in changed:
            continue
        cap, natural, text_px = comp
        shown_now = min(natural, 620)
        cards.append(f"""
<figure class="card">
  <figcaption>
    <b>{entry}</b><br>
    <span class="meta">{path.name} &middot; natural {natural}px &middot;
      lettering {text_px:.0f}px<br>
      now <b>{shown_now}px</b> &rarr; capped <b>{cap}px</b></span>
  </figcaption>
  <div class="pair">
    <div><span class="lbl">now</span>
      <img src="{url}" style="width:{shown_now}px"></div>
    <div><span class="lbl">capped</span>
      <img src="{url}" style="width:{cap}px"></div>
  </div>
</figure>""")

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>#239 image caps</title>
<style>
 body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; background: #f4f6fa;
        color: #1c2330; }}
 .wrap {{ max-width: 1500px; margin: 0 auto; padding: 1.5rem; }}
 h1 {{ font-size: 1.35rem; margin: 0 0 .3rem; }}
 .lede {{ color: #545d6d; max-width: 70ch; margin: 0 0 1.6rem; }}
 .card {{ margin: 0 0 1.6rem; background: #fff; border: 1px solid #e2e5ea;
         border-radius: 8px; padding: 1rem 1.1rem; }}
 figcaption {{ margin-bottom: .7rem; }}
 .meta {{ font-size: .8rem; color: #545d6d; }}
 .pair {{ display: flex; gap: 2rem; align-items: flex-start; flex-wrap: wrap; }}
 .lbl {{ display: block; font-size: .68rem; letter-spacing: .1em;
        text-transform: uppercase; color: #858d9c; margin-bottom: .3rem; }}
 img {{ display: block; background: #fff; border: 1px solid #e2e5ea;
       border-radius: 6px; }}
</style></head><body><div class="wrap">
<h1>#239 &mdash; proposed image caps</h1>
<p class="lede">Each picture as the app draws it today, beside the width that
puts the lettering <em>inside the scan</em> at 16px, the app's body size &mdash;
the same rule the documentation has used since #153. {len(cards)} of
{len(rows)} pictures would change; the rest are already fine and get no cap
at all. Nothing has been written to any file yet.</p>
{''.join(cards)}
</div></body></html>"""
    Path(dest).write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
