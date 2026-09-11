"""Render every entry from the *working tree* into a directory.

Take one of these before a change and one after; `diffsnap.py` says
which drawings moved. Files are written as UTF-8 **bytes** -- the
handover's first trap was a baseline decoded through the console
codepage, which turned every Omega into two characters and reported 284
changed drawings when the real number was 7.
"""
import json
import os
import sys

import common


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    index = []
    rendered = common.render_all()
    for (book, i), (name, svg, err) in sorted(rendered.items()):
        stem = "%s_%03d" % (book.replace(".cir", ""), i)
        if svg is not None:
            with open(os.path.join(outdir, stem + ".svg"), "wb") as f:
                f.write(svg.encode("utf-8"))
        index.append({"book": book, "index": i, "name": name,
                      "stem": stem, "error": err})
    with open(os.path.join(outdir, "index.json"), "wb") as f:
        f.write(json.dumps(index, indent=1).encode("utf-8"))
    errs = [r for r in index if r["error"]]
    print("%d entries -> %s (%d failed)" % (len(index), outdir, len(errs)))
    for r in errs:
        print("  FAIL %s [%s] %s" % (r["book"], r["name"], r["error"]))


if __name__ == "__main__":
    main(sys.argv[1])
