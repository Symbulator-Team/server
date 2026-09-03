"""#239: the contact sheet as a PDF, for reviewing away from this machine.

Same content as `image_caps.py --sheet`, but self-contained: the pictures
are embedded from the docs tree rather than fetched from
learn.symbulator.com, so it can be read on a remote box with no network
and nothing to load.

Each picture appears twice -- as the app draws it today, and at the
computed cap -- at the *ratio* they would appear on screen, scaled to fit
the page. The absolute millimetres mean nothing; the comparison does.

    py tools\\image_caps_pdf.py [-o FILE]

Images are downsampled to the size they are drawn at before embedding,
which is what keeps the file a few megabytes rather than a few hundred.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from image_caps import (BASE, BODY_PX, CARD_PX, DOCS,   # noqa: E402
                        measurements, scan)

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
#: On screen the card is CARD_PX wide; on the page that width becomes this,
#: so the two panels keep their true relative sizes.
SCREEN_TO_PT = (PAGE_W - 2 * MARGIN) * 0.52 / CARD_PX
#: Never embed more pixels than are drawn -- at 2x for a crisp print.
DPI_FACTOR = 2.0


def load_scaled(rel: str, draw_pt: float):
    """The picture, downsampled to what the page actually needs."""
    path = DOCS / rel.replace("/", os.sep)
    if not path.is_file():
        return None, None
    with Image.open(path) as im:
        im = im.convert("RGB")
        want = max(1, int(draw_pt / 72 * 96 * DPI_FACTOR))
        if im.width > want:
            im = im.resize((want, max(1, round(im.height * want / im.width))),
                           Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        buf.seek(0)
        return ImageReader(buf), im.height / im.width


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", default="image_caps.pdf")
    args = ap.parse_args()

    meas = measurements()
    rows = scan(meas)
    todo = [r for r in rows if r[5] and r[5][0] < CARD_PX and r[4] != r[5][0]]

    c = canvas.Canvas(args.out, pagesize=A4)
    c.setTitle("Symbulator #239 - proposed image caps")

    # ---- cover -------------------------------------------------------
    y = PAGE_H - MARGIN - 6 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, y, "#239 - proposed image caps")
    y -= 9 * mm
    c.setFont("Helvetica", 9.5)
    for line in (
        f"{len(todo)} of {len(rows)} pictures would change. The rest are already",
        "fine at full width and get no cap at all.",
        "",
        "Each picture is shown as the app draws it today, then at the width that",
        f"puts the lettering inside the scan at {BODY_PX:.0f}px, the app's body text size -",
        "the same rule the documentation has used since #153. The two panels keep",
        "their true relative sizes; the absolute size on paper means nothing.",
        "",
        "Nothing has been written to any .cir file yet.",
    ):
        c.drawString(MARGIN, y, line)
        y -= 5.2 * mm
    c.showPage()

    # ---- one card per picture ----------------------------------------
    y = PAGE_H - MARGIN
    for path, entry, _i, url, _cur, comp in todo:
        cap, natural, text_px = comp
        rel = url[len(BASE):]
        now_pt = min(natural, CARD_PX) * SCREEN_TO_PT
        cap_pt = cap * SCREEN_TO_PT
        img_now, ratio = load_scaled(rel, now_pt)
        if img_now is None:
            continue
        img_cap, _ = load_scaled(rel, cap_pt)
        h_now, h_cap = now_pt * ratio, cap_pt * ratio
        need = max(h_now, h_cap) + 16 * mm

        if y - need < MARGIN:
            c.showPage()
            y = PAGE_H - MARGIN

        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(MARGIN, y - 4 * mm, entry[:70])
        c.setFont("Helvetica", 7.5)
        c.setFillGray(0.35)
        c.drawString(MARGIN, y - 8 * mm,
                     f"{path.name}  -  natural {natural}px, lettering "
                     f"{text_px:.0f}px  -  now {min(natural, CARD_PX)}px "
                     f"-> capped {cap}px")
        c.setFillGray(0)

        top = y - 13.5 * mm
        c.drawImage(img_now, MARGIN, top - h_now, width=now_pt, height=h_now)
        x2 = MARGIN + (PAGE_W - 2 * MARGIN) * 0.55
        c.drawImage(img_cap, x2, top - h_cap, width=cap_pt, height=h_cap)
        c.setFont("Helvetica", 6.5)
        c.setFillGray(0.5)
        c.drawString(MARGIN, top + 2.2 * mm, "NOW")
        c.drawString(x2, top + 2.2 * mm, "CAPPED")
        c.setFillGray(0)
        y = top - max(h_now, h_cap) - 7 * mm

    c.save()
    size = os.path.getsize(args.out)
    print(f"{args.out}: {len(todo)} pictures, {size/1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
