"""Snapshot every drawing as some past revision drew it.

Swaps `schematic.py` **in place** in the real tree and puts it back in a
`finally`. Both halves of that are the handover's traps:

  * the old file is fetched as **bytes** -- `text=True` decodes git's
    UTF-8 through the console codepage and turns every Omega into two
    characters, which reported 284 changed drawings when the real number
    was 7;
  * swapped in place rather than into a copied package, because the copy
    becomes the variable.

Run it in its own process (it does), so the module is imported fresh
against whichever bytes are on disk.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOLVER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "solver")
TARGET = os.path.join(SOLVER, "symbulator", "schematic.py")


def old_bytes(rev):
    p = subprocess.run(["git", "show", "%s:symbulator/schematic.py" % rev],
                       cwd=SOLVER, capture_output=True)
    if p.returncode:
        raise SystemExit("git show failed: %s" % p.stderr.decode(
            "utf-8", "replace"))
    return p.stdout


def main(rev, outdir, script="snapshot.py"):
    want = old_bytes(rev)
    with open(TARGET, "rb") as f:
        keep = f.read()
    if want == keep:
        print("note: %s is what is already on disk" % rev)
    try:
        with open(TARGET, "wb") as f:
            f.write(want)
        # A fresh interpreter, so the swapped file is the one imported.
        r = subprocess.run([sys.executable, script, outdir],
                           cwd=os.path.dirname(os.path.abspath(__file__)))
        rc = r.returncode
    finally:
        with open(TARGET, "wb") as f:
            f.write(keep)
        with open(TARGET, "rb") as f:
            assert f.read() == keep, "RESTORE FAILED -- fix by hand"
        print("restored %s" % TARGET)
    raise SystemExit(rc)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else "snapshot.py")
