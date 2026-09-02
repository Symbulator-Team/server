# Symbulator version X — the server

**You are holding version X, not version 9.** Read this before changing
anything, and before deploying anything anywhere.

Symbulator is Roberto Perez-Franco's symbolic linear-circuit simulator,
begun in 1999 on a TI-89 and ported to Python and SymPy as version 9.
**Version 9 is canonical**: he created and maintains it. **Version X is a
collaborative fork**, created 30 Aug 2026, where new ideas are tried
before any of them is proposed back.

|  | version 9 (canonical) | version X (this) |
|---|---|---|
| GitHub | `Symbulator` | `Symbulator-Team` |
| PythonAnywhere | `symbulator.pythonanywhere.com` | **none — the SymbulatorX account was shut down by PythonAnywhere, 2 Sep 2026.** X is source only until it has a new home; `symbulatorx.pythonanywhere.com` is a 404 |
| landing + docs | symbulator.com, learn.symbulator.com | **none — version 9's alone** |
| offline builds | install.symbulator.com, symbulator.com/9/local.zip | **none** |

## The rules that matter

**X's banner is X's own, and a merge from v9 will fight you for it.**
Since 2 Sep 2026 the wordmark reads **Symbulator X**, not `Symbulator
9β`, and the subtitle is *testing the limits of symbolic simulation*.
Both live in `templates/index.html` **and** `templates/eqsheet.html`, on
lines version 9 also owns, so `git merge v9/main` will conflict there
whenever v9 touches its banner: **keep X's side, take v9's for
everything else.** It is the only deliberate content difference between
the two trees, so a conflict anywhere else in those files is a real one
to read rather than a known collision.

Why it exists is worth knowing, because it is not decoration. On 2 Sep
2026 PythonAnywhere disabled the `symbulatorx` account for content that
"might be related to phishing activities". X was at that moment a
byte-identical copy of `symbulator.pythonanywhere.com` under a hostname
one letter away, on a different account — which is precisely what an
automated scanner reads as a phishing clone. A visibly distinct banner
is the honest fix as well as the safe one: a stranger landing on X could
not previously tell it was not the real thing.

The subtitle is `notranslate`. X is English-only, and marking it so is
what keeps `python tools/i18n.py check` clean — changing a translated
string would otherwise orphan its key in all twelve dictionaries and
demand twelve translations this fork has a standing rule not to do.

**Never deploy this to any of version 9's five sites.** Not
`install.symbulator.com`, not `symbulator.com`, not
`learn.symbulator.com`, not `symbulator.pythonanywhere.com`. Some
documents in this repository predate the fork and still describe version
9's deploys; they are describing what *version 9* does. Version X deploys
to one place, below.

**The documentation and the landing page belong to version 9.** X has no
docs site. The app links out to `learn.symbulator.com` in two places —
the ribbon's *Tutorial* and the About card's *Acknowledgements* — and
those are deliberately left pointing at version 9's tutorial. A reader on
X can therefore be shown a tutorial describing an interface X has since
changed. Live with it, or reword those links; do not try to publish docs.

**`NEXT.md` in the `local` repository is version 9's record**, numbered
#59 to #182 and still running. Do not continue that sequence here — two
projects would both claim #183. Version X numbers its own items **X1, X2,
X3…**, which can never collide.

## Deploying version X

PythonAnywhere account `SymbulatorX`, a clone of this repository at
`~/symbulator_web`, Python **3.12**, virtualenv `symbulator-venv`:

    cd ~/symbulator_web && source ~/.virtualenvs/symbulator-venv/bin/activate && git pull

then **Reload** on the Web tab. Check `/healthz`: it reports the build the
running process started with *and* the build on disk, so a pull without a
reload shows up in one request.

Then **actually use the site** — load it and run a real solve. A clean
`git pull` does not catch a crash that only appears on a request.

Free-tier notes, both learned the hard way setting this account up: the
virtualenv's Python must match the web app's (3.12), and the 512 MB quota
is tight enough that `pip install` needs `--no-cache-dir` after a
`pip cache purge`. numpy and scipy do fit.

## Bringing version 9's improvements in

Each clone here carries a second remote, `v9`, pointing at the canonical
repository:

    git fetch v9 && git merge v9/main

Its **push** URL is deliberately broken (`DO-NOT-PUSH-TO-VERSION-9`) so a
mistyped push cannot put experimental work in the canonical repository. Do
not repair it.

Sending an experiment the other way, into version 9, is a **pull request**
on GitHub from `Symbulator-Team/server` to `Symbulator/server`. That is
the only route, and Roberto reviews it. These are GitHub forks precisely
so that route exists.

Keeping the diff against version 9 small keeps those merges clean. Prefer
adding a file over rewriting one.

## What is in here

The whole backend and the whole frontend, and they are each one file.

- **`app.py`** (933 lines) — every route, input validation, and the
  subprocess-with-timeout that runs a solve.
- **`symbulator_ui.py`** (3,624 lines) — the layer between the web app and
  the solver package: parsing what the reader typed, formatting every
  answer, the notes explaining what it did with their input. **Most
  behaviour a user would call "the app" lives here, not in the solver.**
- **`templates/index.html`** (5,040 lines) — the entire frontend: markup,
  CSS and JavaScript inline, one page, no build step, no framework.
- **`circuitbook.py`** — reader and writer for the `.cir` input-file
  format. `examples/Showcase.cir` documents that format in its header.
- **`eqsheet.py`** — the Numerical Solver at `/eqsheet/`, a Flask
  blueprint. numpy and scipy are imported *inside* its handlers, so the
  app starts and solves fine without them; only this page needs them.
- **`examples/`** — 20 `.cir` files, 330 entries, the built-in examples.
  Listed from disk on every request, so adding one needs no restart.
- **`static/mathjax/`** — MathJax served locally, no CDN.

`DEPLOY.md`, `EQSHEET.md`, `ROADMAP.md` and `tools/README.md` are version
9's and still accurate about the code; read their deploy sections as
history, not instructions.

## Two things that will bite you

**`templates/index.html` is a Jinja template.** On 30 Aug 2026 an HTML
comment in it contained `{#`, which is Jinja's comment-opener, with no
closing `#}`. The template stopped parsing and the server returned **500
on every page** — while `/healthz`, which renders no template, stayed
green and reported a healthy build. **A template change is not verified
until Flask has rendered it.** After touching anything under `templates/`,
run the app and fetch `/`, `/eqsheet/` and `/healthz`:

    python app.py      # then curl those three

Watch for `{#`, `{%` and `{{` in comments and in JavaScript especially,
since none of them look like template syntax to a reader.

**The examples are a regression suite.** `tools/verify_lesson.py` runs
every entry of one `.cir` book through the real app and prints what a
reader would see beside the answer the tutorial prints:

    cd tools && py verify_lesson.py Lesson_03 --quiet

A clean book reports `0 entr(ies) with a problem`. All 18 do, with one
deliberate exception: Lesson 4's *Bo2's Example 3.11 (Tricky, as it
comes)*, which the tutorial teaches **as** a failure. If a change makes
other entries disagree, the change is wrong — those answers are checked
against Roberto's printed originals.

## The solver is a separate package, and X runs version 9's

`requirements.txt` pins **`symbulator` from PyPI**, which is version 9's
published solver. So `Symbulator-Team/solver` — the fork of the solver —
**has no effect on this app until you deliberately install it**:

    pip install -e ../solver        # or wherever your checkout is

Do that before concluding a solver change did nothing. Do not publish a
second package to PyPI as a first move; see that repository's own
`CLAUDE.md`.
