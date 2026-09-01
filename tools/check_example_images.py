# -*- coding: utf-8 -*-
"""#219: keep the examples' `image:` links honest.

An entry in `examples/*.cir` may carry an `image:` line naming a picture
of its circuit. Those pictures are **not** in this repository: they are
the tutorial's own figures, served from `learn.symbulator.com`, and they
live in the *docs* tree at `Sym Docum/Documentation/assets/`.

That crossing is the whole reason this script exists. Nothing else
connects the two: a figure renamed, re-slugified or deleted on the docs
side leaves a dead link here, and a dead link does not look broken --
the app hides the picture's card when the image fails to load, by
design, so the page stays tidy and the reader simply never learns there
was supposed to be a circuit there. The failure is *silent*, which is
the kind this project has been bitten by before (see "A guard nobody has
watched fail is not a guard" in the shared CLAUDE.md).

So: every `image:` URL must name a file that exists in the docs tree.

    py tools/check_example_images.py           # against the docs tree
    py tools/check_example_images.py --live    # also fetch each one

`--live` is the stronger check and the slower one -- it fetches every
distinct URL from the real site, which is the only way to catch a figure
that exists locally but was never deployed. Run the plain form often and
the live form before anything ships.

Exit status is 0 when every link resolves, 1 otherwise.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent
EXAMPLES = SERVER / "examples"

# The docs tree, which must sit beside the app tree. `build.py` on the
# docs side reaches across the same way to copy banner.css, and fails
# with the same kind of message when the layout is not what it expects.
DOCS = SERVER.parent.parent.parent / "Sym Docum" / "Documentation"

BASE = "https://learn.symbulator.com/"
IMAGE_RE = re.compile(r"^image:\s*(?P<url>\S+)\s*$")


def collect() -> list[tuple[str, str, str]]:
    """Every image link in the example books, as (file, entry, url)."""
    found: list[tuple[str, str, str]] = []
    section = re.compile(r"^\[(?P<name>.+)\]\s*$")
    for path in sorted(EXAMPLES.glob("*.cir")):
        entry = "(before the first entry)"
        for line in path.read_text(encoding="utf-8").splitlines():
            m = section.match(line.strip())
            if m:
                entry = m.group("name").strip()
                continue
            m = IMAGE_RE.match(line)
            if m:
                found.append((path.name, entry, m.group("url")))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true",
                    help="also fetch every distinct URL from the live site")
    args = ap.parse_args()

    links = collect()
    urls = sorted({u for _, _, u in links})
    print(f"{len(links)} image links across the example books, "
          f"{len(urls)} distinct pictures")

    if not DOCS.is_dir():
        print(f"\ncheck_example_images.py: cannot find the docs tree at {DOCS}.\n"
              "  The examples' pictures are the tutorial's own figures, which\n"
              "  live in that tree; this check needs 'Sym Docum' to sit beside\n"
              "  'Symbulator'. Restore the layout, or run this where it does.",
              file=sys.stderr)
        return 1

    problems = 0

    # 1. Every link must name a file that exists in the docs tree.
    for name, entry, url in links:
        if not url.startswith(BASE + "assets/"):
            print(f"  {name}: '{entry}' -- {url}\n"
                  f"      not a {BASE}assets/ link", file=sys.stderr)
            problems += 1
            continue
        rel = url[len(BASE):]
        if not (DOCS / rel.replace("/", os.sep)).is_file():
            print(f"  {name}: '{entry}' -- {url}\n"
                  f"      no such file in the docs tree", file=sys.stderr)
            problems += 1

    if problems:
        print(f"\ncheck_example_images.py: {problems} broken link(s).\n"
              "  A picture was renamed or removed on the docs side. Either put\n"
              "  it back, or update the image: line that names it -- the app\n"
              "  hides the card when an image fails, so this never shows up as\n"
              "  a visible fault on the page.", file=sys.stderr)
        return 1
    print("every link names a file that exists in the docs tree")

    # 2. Optionally, prove they are actually served.
    if args.live:
        import time
        import urllib.error
        import urllib.request
        from concurrent.futures import ThreadPoolExecutor

        def head(url: str):
            """HEAD with retries. A connection error is not evidence that a
            picture is missing -- fetching a few hundred files quickly gets
            throttled, and an early version of this check reported 23 dead
            links that were all serving 200 when asked again one at a time.
            Only an HTTP status is taken at face value; a transport failure
            is retried, and reported as "could not reach" rather than as a
            broken link, so this check never cries wolf."""
            last = ""
            for attempt in range(4):
                try:
                    req = urllib.request.Request(
                        url, method="HEAD",
                        headers={"User-Agent": "Mozilla/5.0 (compatible; "
                                               "symbulator-check-example-images)"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        return url, resp.status, resp.headers.get("Content-Type", "")
                except urllib.error.HTTPError as exc:
                    return url, exc.code, ""      # a real answer: believe it
                except Exception as exc:          # noqa: BLE001
                    last = type(exc).__name__
                    time.sleep(1.5 * (attempt + 1))
            return url, last, ""

        dead = []
        # Gently: this is someone's shared host, and speed here buys
        # nothing but throttling.
        with ThreadPoolExecutor(max_workers=3) as pool:
            for url, status, ctype in pool.map(head, urls):
                if status != 200 or not ctype.startswith("image/"):
                    dead.append((url, status, ctype))
        if dead:
            missing = [d for d in dead if isinstance(d[1], int)]
            unreachable = [d for d in dead if not isinstance(d[1], int)]
            for url, status, ctype in missing:
                print(f"  {url} -> HTTP {status} {ctype}".rstrip(), file=sys.stderr)
            for url, status, _ in unreachable:
                print(f"  {url} -> could not reach ({status})", file=sys.stderr)
            if missing:
                print(f"\ncheck_example_images.py: {len(missing)} link(s) are "
                      "not served.\n"
                      "  They exist locally, so this is a deploy that has not "
                      "happened:\n"
                      "  run `py deploy_symbulator.py learn` from "
                      r"C:\Users\perez\Claude Code" ".", file=sys.stderr)
                return 1
            print(f"\ncheck_example_images.py: {len(unreachable)} link(s) could "
                  "not be reached\n"
                  "  after retrying. That is a network or throttling problem, "
                  "not a broken\n"
                  "  link -- re-run before reading anything into it.",
                  file=sys.stderr)
            return 1
        print(f"all {len(urls)} pictures return 200 and an image type from "
              "the live site")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
