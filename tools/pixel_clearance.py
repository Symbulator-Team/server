"""Pixel truth: how close does a label's ink come to a symbol's ink?

`review_schematics.py` answers that from geometry -- estimated text
metrics against the boxes the canvas records. This answers it from the
rendered picture, and exists because the estimate was wrong in a way
geometry could not see: `stroke-linejoin="miter"` runs a zigzag's peak
2.2px past its own vertex, so labels the path said were 3px clear of a
resistor were 1px clear of its ink, which a reader sees as touching.

How it works. Each drawing is rendered by headless Chrome with the
labels forced to pure red and every stroke to pure blue, at SCALE x.
A pixel's ink is read from the channel it *removes* from white -- red
ink takes the blue channel down, blue ink takes the red channel down --
so a faint antialiased red (255,243,243) is 12/255 of red and no blue.
Reading that as "the two channels are close, so both inks are here" is
what made the first version of this call every drawing a collision.
The blue mask is then grown one ring at a time until it meets the red
one, and the ring count is the clearance.

    py pixel_clearance.py                  # the built-in sample
    py pixel_clearance.py --all            # every entry of every book
    py pixel_clearance.py --all --min 3    # fail below 3px

Needs Chrome, numpy and Pillow, none of which the package depends on --
which is why this is a separate tool and not part of the fast harness.
Roughly a second per drawing, so --all is a twenty-minute run: use
review_schematics.py routinely and this one after anything that changes
a symbol's shape, its stroke, or where a label sits.
"""

import argparse
import io
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

# Circuit values carry Ohm and micro; a console on a legacy code page can
# encode neither, and a report that dies while printing its own findings
# loses the whole run -- which is what the first full sweep did, after
# thirty-five minutes and with twenty-one findings to show for it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TOOLS = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(TOOLS)
SOLVER = os.path.join(os.path.dirname(SERVER), "solver")
if os.path.isdir(os.path.join(SOLVER, "symbulator")):
    sys.path.insert(0, SOLVER)
sys.path.insert(0, SERVER)

from symbulator.schematic import to_svg            # noqa: E402
from circuitbook import parse_book                 # noqa: E402

EXAMPLES = os.path.join(SERVER, "examples")
SCALE = 4          # device pixels per SVG px
INK = 32           # 1/8 coverage; below this a pixel is antialias haze
PROBE = 20         # give up looking past this many device pixels

CHROME_CANDIDATES = [
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "google-chrome", "chromium",
]
CSS = ("<style>html,body{margin:0;padding:0;background:#fff}"
       "svg{color:#00f;display:block}"
       ".symbulator-schematic .lbl{fill:#f00!important}</style>")


def _chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c) or "/" not in c:
            return c
    raise SystemExit("no Chrome or Edge found; edit CHROME_CANDIDATES")


def render(svg, work):
    html = os.path.join(work, "clearance.html")
    png = os.path.join(work, "clearance.png")
    io.open(html, "w", encoding="utf-8").write(CSS + svg)
    subprocess.run([_chrome(), "--headless=new", "--disable-gpu",
                    "--user-data-dir=" + os.path.join(work, "profile"),
                    "--screenshot=" + png, "--hide-scrollbars",
                    "--window-size=2400,1700",
                    "--force-device-scale-factor=%d" % SCALE,
                    "file:///" + html.replace("\\", "/")],
                   capture_output=True)
    return np.asarray(Image.open(png).convert("RGB")).astype(np.int16)


def masks(a):
    """(label mask, symbol mask). A pixel carrying both inks is in
    both -- that is what an actual overlap looks like."""
    red, blue = 255 - a[:, :, 2], 255 - a[:, :, 0]
    both = (red >= INK) & (blue >= INK) & (abs(red - blue) <= 6)
    return (((red >= INK) & (red > blue + 6)) | both,
            ((blue >= INK) & (blue > red + 6)) | both)


def _grow(m):
    g = m.copy()
    g[1:, :] |= m[:-1, :]
    g[:-1, :] |= m[1:, :]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    return g


TEXT_RE = re.compile(
    r'<text[^>]*x="([-\d.]+)" y="([-\d.]+)" text-anchor="(\w+)">(.*?)</text>')
VIEWBOX_RE = re.compile(
    r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')


def _nearest_label(svg, x, y):
    """Which label sits at (x, y) in SVG user coordinates -- the one
    whose anchor point is nearest. Enough to name an offender in a
    report, which is all this is for."""
    best, how_far = "?", 1e9
    for m in TEXT_RE.finditer(svg):
        lx, ly = float(m.group(1)), float(m.group(2))
        d = ((lx - x) ** 2 + (ly - y) ** 2) ** 0.5
        if d < how_far:
            how_far, best = d, re.sub(r"<[^>]*>", "", m.group(4))
    return best


def clearance(svg, work):
    """(smallest clear distance in SVG px, the label responsible).
    0.0 means the two inks share a pixel; (None, None) means the
    drawing has no labels, or no symbols, to compare.

    The label is named from the *first* closest-approach pixel, so a
    drawing with two equally tight spots reports one of them; fix that
    and the next run names the other."""
    label, symbol = masks(render(svg, work))
    if not label.any() or not symbol.any():
        return None, None
    vb = VIEWBOX_RE.search(svg)
    x0, y0 = (float(vb.group(1)), float(vb.group(2))) if vb else (0.0, 0.0)
    grown = symbol
    for ring in range(PROBE + 1):
        hit = grown & label
        if hit.any():
            ys, xs = np.nonzero(hit)
            return (ring / float(SCALE),
                    _nearest_label(svg, x0 + xs[0] / SCALE,
                                   y0 + ys[0] / SCALE))
        grown = _grow(grown)
    return PROBE / float(SCALE), None


def entries(all_books):
    if not all_books:
        return [("divider", "e1,1,0,5:r1,1,2,1'k:rin,2,0,2'k"),
                ("series RLC", "e1,1,0,10:r1,1,2,50:l1,2,3,0.1:c1,3,0,1'u"),
                ("parallel L C", "j1,0,1,2:l1,1,0,0.5:c1,1,0,1'm:ra,1,0,10"),
                ("op-amp", "es,1,0,1:r1,1,2,10'k:rf,2,3,100'k:o1,2,0,3"),
                ("coupled", "e1,1,0,10:l1,1,2,0.2:r1,2,0,50:l2,3,0,0.3:"
                            "rl,3,0,25:m1,l1,l2,0.1")]
    out = []
    for book in sorted(f for f in os.listdir(EXAMPLES) if f.endswith(".cir")):
        with io.open(os.path.join(EXAMPLES, book), encoding="utf-8") as f:
            circuits, _warnings, _title = parse_book(f.read())
        out += [("%s / %s" % (book, c["name"]), c["desc"]) for c in circuits]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="every entry of every book in ../examples")
    ap.add_argument("--min", type=float, default=3.0,
                    help="fail below this clearance, in SVG px")
    ap.add_argument("--work", default=os.path.join(
        os.environ.get("TEMP", "/tmp"), "symbulator_clearance"))
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)

    rows, worst = [], []
    for i, (name, desc) in enumerate(entries(args.all)):
        try:
            gap, culprit = clearance(to_svg(desc), args.work)
        except Exception as ex:                       # noqa: BLE001
            print("FAIL  %s: %s" % (name, ex))
            worst.append((-1.0, name, desc, "?"))
            continue
        if gap is None:
            continue
        rows.append((gap, name, desc, culprit))
        if gap < args.min:
            worst.append((gap, name, desc, culprit))
        if args.all and i % 25 == 0:
            print("  ... %d done" % i, file=sys.stderr)

    rows.sort(key=lambda r: r[0])
    print("\ntightest ten:")
    for gap, name, _desc, culprit in rows[:10]:
        print("  %5.2f px  %-50s  label %r" % (gap, name[:50], culprit))
    print("\n%d drawings, tightest %.2f px, threshold %.2f px, %d below"
          % (len(rows), rows[0][0] if rows else -1, args.min, len(worst)))
    for gap, name, desc, culprit in worst:
        print("  BELOW %5.2f px  %s  label %r"
              % (gap, name, culprit))
        print("        %s" % desc)
    return 1 if worst else 0


if __name__ == "__main__":
    sys.exit(main())
