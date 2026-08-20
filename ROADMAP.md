# Symbulator — pending work

Running notes so nothing is lost between sessions.

## Next build TODO — Dark Mode toggle (20 Aug 2026)

Roberto wants a toggle to switch to Dark Mode, across all three
user-facing surfaces:

* the server (Flask) interface — `server/templates/index.html`
* the local (offline/Pyodide) interface — generated from the same
  template by `build_local.py`, so implementing it once in the shared
  template covers both automatically, same as every other UI change
* the web version of the documentation (the CoderDocs tutorial/docs
  site — `learn.symbulator.com` once that move happens; see the domain
  note below for where those pages currently live)

Not implemented yet — noted here per Roberto's explicit "put that in
the To-Do list for the next build," not built this round. When it's
picked up: check whether the docs site uses the same CSS system as the
app template or a separate CoderDocs stylesheet, since the toggle will
likely need two different implementations (app template vs. docs site)
even though it's one feature from Roberto's point of view.

## Next build TODO — real domains are settling (19 Aug 2026)

Roberto has named two subdomains for the live site, replacing the
placeholder domains used in the docs so far:

* **`py.symbulator.com`** — the server (Flask) version of the Python
  port, i.e. this app. Roberto is testing it on cPanel now (not
  `symbulator.perez-franco.com`, which was only ever an example in the
  docs — nothing in the app code hardcodes a domain, so this needed no
  code change to work).
* **`learn.symbulator.com`** — the tutorial/docs site (the CoderDocs
  pages: `docs-page7.html`/`docs-page8.html`/`docs-pagepy.html` and
  their `index*.html` landing pages, currently referenced from
  `symbulator.com` and cross-linked between each other).

Next time the docs get a pass, update the example/reference domains in:

* `server/DEPLOY.md` (cPanel section, currently says
  `symbulator.perez-franco.com`)
* `ROADMAP.md` (the deploy-target mentions of `symbulator.perez-franco.com`
  / `symbulator.roberto.au`)
* the tutorial site's own internal links/canonical URLs, once its actual
  hosting location moves to `learn.symbulator.com`

to the real domains above, once Roberto confirms they're final. Don't do
this yet — he said explicitly not to update it until then, this is just
the running note so nothing gets lost.

## "Download the offline version" section — 18 Aug 2026

The server version now links to the local (Pyodide) version's download,
in a new card near the bottom of the page ("Run it offline, with no
internet needed"), so a visitor to the hosted site can get the offline
app without knowing it exists as a separate project.

* **`server/static/downloads/symbulator-local.zip`** — a self-contained
  copy of `local/` (index.html, the Python modules, `vendor/`,
  `static/mathjax/`) plus three convenience extras not otherwise part
  of `local/`: `start.sh` / `start.command` / `start.bat` (each starts
  `python3 -m http.server` and opens the browser automatically) and a
  plain-language `README.txt`. Served as a normal Flask static file, so
  no server code was needed beyond dropping the zip in place.
* **`scripts/build_local_download.sh`** builds that zip reproducibly:
  checks `local/vendor/` exists and `local/index.html` is not stale,
  stages `local/`'s shippable files (skipping the maintainer-only
  `build_local.py` and `local/README.md`), adds the three extras from
  the new `scripts/local_download_extras/`, and zips it into
  `server/static/downloads/`. Re-run whenever `local/` changes.
  `server/static/downloads/` is gitignored, same as the other large
  fetched/built assets.
* **`build_local.py` strips the new card from the offline build itself**
  — "download the offline version" would be circular once you're
  already running it. The template marks the card with
  `<!-- server-only: ... -->` / `<!-- /server-only -->` comments; a new
  `strip_between()` helper removes everything in between and, like
  every other substitution in that script, raises if the markers ever
  go missing rather than silently shipping the card into the offline
  build. `sw.js`'s `CACHE_VERSION` bumped to `symbulator-v6`.

Verified: 85 package tests; `/tmp/regress.py`; `/tmp/test_page.js`
against both front ends (confirmed the card and download link exist on
the server version and are absent from the local version, and actually
clicked the link and checked the downloaded file's size);
`/tmp/test_offline.js` re-confirmed with the new cache version; and, as
an end-to-end check outside the harness, actually downloaded the real
zip the server serves, unzipped it into a clean directory, ran
`start.sh`, and ran the full Playwright suite against the result —
exactly what a visitor downloading it would experience.

## UI polish pass — 18 Aug 2026

Roberto's second feedback round on the server version's interface
(numbered N0–N10), built after an explicit "note down, don't compile
yet" hold and then an explicit "proceed":

* **`symbulator` 0.4.1** — `__version__` added as the single source of
  truth (`pyproject.toml` reads it via `dynamic = ["version"]`); two new
  tests confirm it is exposed and matches the installed distribution.
  0.4.0 is what's live on PyPI; 0.4.1 is built locally, not yet
  published (holding for the GitHub release workflow).
* **Clearer complex-value warning.** A value like `5*i` outside AC now
  explains *both* possible mistakes — "if you meant a complex source,
  switch to AC" and "if you meant an ordinary variable, i/I/j/J are
  reserved, only the bare letters, so `ix`/`i1`/`i_load` are fine" —
  instead of one terse line.
* **Notes were being dropped on the error path.** `/api/solve` (and the
  local bridge) only attached `notes` to *successful* responses, so the
  "normalised '5\*i' to '5j'" explanation vanished exactly when it was
  most needed, alongside the error it explains. Fixed in both.
* **Describe / Simulate split into two cards** — the two were one card;
  now separate, using the same `.card` visual break already used
  elsewhere on the page.
* **Auto-growing description textarea** (was a fixed small box).
* **Header**: "Symbulator · Py" → "Symbulator Py"; the top link now
  reads "Learn how to use" instead of "Documentation".
* **"open file…" renamed "Upload File"**, moved from the bottom actions
  bar to directly under the description textarea, next to the example
  picker.
* **Circuit syntax reference and Circuit file format now sit side by
  side** under Describe, instead of file format being a separate card
  far below the fold. The syntax reference gained an intro paragraph
  (one element per line, fields by comma, node 0 is ground) with a link
  to the documentation and a nudge toward the example circuits.
* **ω moved to its own row**, beneath Tool / Analysis rather than
  crowded into the same row as Variables/Node 1/Node 2/Parameters.
* **Run button widened** so it doesn't read as just another button.
* **Evaluate / Solve**: the inline "e.g. ..." example text is now a
  collapsed "Examples" details block, so the label reads "in terms of
  the results above" without a wall of comma-separated samples attached.
* **Live file of circuits (N10)** — replaces the old one-shot "save
  circuit as .sym". The browser now holds a live list of circuits
  (starting from the built-in examples, or replaced wholesale by
  *Upload File*); "add this circuit to the file" appends or updates an
  entry by name, "download the file" writes the whole live list out as
  one `.sym` file. `/api/export` (and `bridge.py`'s `export_book`) were
  rewritten from a single flat circuit to `{"circuits": [...]}`, a list
  of already-array-shaped circuit dicts, reusing `circuitbook.format_book`
  and `MAX_CIRCUITS`/`MAX_NAME_LEN` for the cap. `build_local.py`'s
  export substitution was updated to match; `sw.js`'s `CACHE_VERSION`
  bumped to `symbulator-v5`.

Verified: 85 package tests; `/tmp/regress.py` (added multi-circuit and
empty/blank-description export checks); `/tmp/test_page.js` against
both front ends (added checks for the auto-grow textarea, the Upload
File rename, the side-by-side syntax/file-format panels, ω's own row,
the widened Run button, and the full add-to-file/download-file flow,
including reading the downloaded `.sym` back to confirm its contents);
`/tmp/test_offline.js` re-confirmed the local version still boots,
solves and lists examples with the network cut, from the new
`symbulator-v5` cache. Copied into `/tmp/symbulator-repo/{server,local}`
and committed there, still not pushed — Roberto asked to hold until he
has tested both versions locally on his own machine.

## Recompile pass — 18 Aug 2026

Roberto's full feedback round (wording, layout, prefixes, imaginary
unit, case folding) is built and verified. What changed this pass, on
top of the wording work:

* **`symbulator` 0.4.0** — SI prefixes now stop at peta so `E` belongs
  to scientific notation; both micro characters (U+00B5 and U+03BC)
  accepted; `safe_sympify` turns every unknown identifier into a plain
  Symbol so `Q`, `S`, `N`, `beta`, `gamma` and `E` stop being hijacked
  by SymPy's own objects; element names, element prefixes and node names
  fold to lowercase while *values* keep their case (`4.7'M` ≠ `4.7'm`);
  `ex()` no longer accepts TR, matching the calculator's own
  "1:DC 2:AC 3:FD" prompt. 83 tests pass.
* **Merged rounding control** — one dropdown: exact / approximate /
  approximate to *n* significant digits (n = 2…12). The old "force
  decimals" checkbox is gone. Choosing SI prefixes while exact is
  selected is contradictory, so each side now nudges the other,
  symmetrically.
* **Imaginary unit** — `i`, `I` and `j` are all accepted and normalised
  to `j` before solving, including inside the circuit description; bare
  `j` becomes `1j`. Output is IEEE house style: upright `j` via
  `sp.latex(expr, imaginary_unit="tj")`. Complex values outside AC are
  refused with an explanation rather than silently mis-solved.
* **Notes are now displayed.** They were computed and returned but never
  rendered — normalisation, hijacked names and the new impulse warning
  were all invisible. They now appear in a warning block above the
  results, in both front ends.
* **Transient dispatch fixed.** `solve_ui` routed *every* domain through
  `ex()`, which had just lost TR, so the TR option in the dropdown
  failed outright. TR now calls `tr()` directly. Expert Mode still has
  no TR, deliberately.
* **Impulse warning.** In FD/TR a source written as a plain number is an
  impulse, so its node reads 0 for every t > 0 — mathematically right,
  and baffling the first time. The page now says so and suggests
  `10/s`.
* **"Real solutions only"** in the Solve panel — the difference between
  the calculator's `solve` and `cSolve`. Off by default.
* **`build_local.py`** — the local version is now *generated* from the
  server template by a checked script (`--check` verifies it is not
  stale). Hand-editing the two pages in parallel is what let the service
  worker go missing in the previous build.
* Favicon on the server version; MIT `LICENSE` in all three projects.

Verified: 83 unit tests, 44 HTTP checks against the server version, 32
browser checks against *each* front end, plus a network-disabled run
proving the local version boots and solves from cache alone
(`/tmp/regress.py`, `/tmp/test_page.js`, `/tmp/test_offline.js`).

## Requested, not yet built

### (built 17 Aug 2026) Equation solver — the "Solve" panel
Delivered: a Solve panel below Evaluate. Equations (one per line) plus
an optional "solve for" list; the circuit's answers are substituted in
first, with variables accepted in both spellings (`v_2` / `v2`,
`i_r1` / `ir1`) via the shared `_alias_mapping` helper that the
evaluator also uses. Backed by `sympy.solve`; reports every root when
there are several, says plainly when there is none, and honours all the
Settings (rounding, SI prefixes, units, force decimals). A variable
named in "solve for" is deliberately excluded from the substitution so
it stays an unknown. Endpoint: `POST /api/solveq`.

Nothing outstanding on this item.

## Browser build (PWA) — BUILT 17 Aug 2026

Delivered as `symbulator_browser/`. Static files, no server: Pyodide
runs CPython + SymPy + the `symbulator` wheel in the visitor's tab.

Decisions taken (Roberto, 17 Aug): background boot (no precompiled
bytecode, no IndexedDB caching); keep the Flask build alongside; offline
via installable PWA rather than a zip/installer.

**One shared brain.** `symbulator_ui.py` now holds all solving,
formatting, units, element ordering and variable aliasing, and is used
*byte-identically* by both front ends — Flask runs it in a killable
subprocess, the browser loads it into Pyodide. `app.py` shrank from
1049 to 414 lines and is now only the HTTP layer. If you edit
`symbulator_ui.py` or `circuitbook.py`, copy the file to the other
project.

**Measured after warm-up tuning:** background boot 8.0 s (page usable
throughout), then solves at **0.02–0.04 s** — faster than the Flask
version, which pays HTTP plus a subprocess spawn. The boot deliberately
imports sympy *and* runs one throwaway solve, because sympy builds
internal caches on first use; without that the cost landed on the
user's first click (4.2 s) instead of on the background boot.

Verified end to end in a headless browser: DC/AC/transient, the
ambiguity question and rewrite, Thevenin, evaluate, solve-equations,
examples, file upload, .sym export — and **offline operation** after
the service worker cached 17 files (solved a divider with the network
disabled and the server stopped).

Known cosmetics: the header still reads "Symbulator · online", which is
odd for an offline install; consider dropping "· online" or making it
conditional.

### Next steps for the browser build
- Upload to symbulator.perez-franco.com and symbulator.roberto.au. Check
  the host serves `.wasm` as `application/wasm` (see its README) and that
  HTTPS is on, which the service worker requires.
- Optional later: precompiled bytecode or IndexedDB bytecode caching to
  halve the 8 s boot; a native installer (PyInstaller/Tauri) if a
  conventional .exe is ever wanted.

## Appendix — the original Pyodide prototype measurements (17 Aug 2026)

**Verdict: viable.** The whole of Symbulator was run inside a headless
browser with no server: DC, AC, transient (inverse Laplace), Thevenin
and expert mode all returned the same answers as the Flask version. The
published `symbulator` wheel installs into Pyodide unmodified, because
it is pure Python and SymPy 1.14 / mpmath ship with Pyodide.

Measured (headless Chromium, local server):

| phase | time |
|---|---|
| boot Pyodide (WASM + CPython) | ~3.0 s |
| load sympy + mpmath | ~0.9 s |
| **import sympy (first)** | **3.8 s** |
| load + import symbulator wheel | 0.06 s |
| first DC solve | 0.26 s |
| **cold start to first answer** | **~8 s** |
| warm DC solve | **17 ms** |
| warm AC solve | ~0.5 s |
| warm transient (inverse Laplace) | ~0.36 s |

Download: 18.2 MB raw, **12.2 MB gzipped** (~4 s at 25 Mbps, ~1 s on
fibre, ~20 s on poor mobile). Note the sympy wheel used was PyPI's,
which includes tests; Pyodide's own build unvendors them and would be
smaller.

Key finding: **3.4 s of the 3.8 s sympy import is bytecode
compilation.** Forcing `compileall` inside Pyodide and re-importing
dropped the import to **401 ms** — a 90% cut, which would take cold
start from ~8 s to ~4 s. Bytecode is bulkier than source, so this
trades download size for startup time; measure both before deciding.
(Bytecode is Python-version specific — it must be built with Pyodide's
own CPython 3.14, not on a dev machine.)

Bigger lever than any optimisation: **boot Python in the background**
while the page is already interactive. The user types a circuit (ten
seconds of typing) while Python loads, so the cold start is hidden
rather than blocking.

Warm solves are *faster than the Flask version* (17 ms vs 100–500 ms),
since there is no HTTP round trip and no subprocess spawn.

### Questions — answered 17 Aug 2026
1. Precompiled bytecode? **No** — background boot only.
2. Replace Flask? **No** — keep both.
3. Offline delivery? **Installable PWA.**

### Why this matters for hosting
A browser-only build is static files. It needs no "Setup Python App",
no subprocess permissions, no memory limits — so it runs on
symbulator.perez-franco.com and symbulator.roberto.au as plain uploads,
and doubles as the downloadable offline app. Prototype lives in
/tmp/pyodide_proto (sandbox, ephemeral) — rebuild from these notes.

## Outstanding tasks

- ~~Publish `symbulator` 0.4.0 to PyPI~~ **DONE 18 Aug 2026** — live at
  https://pypi.org/project/symbulator/0.4.0/. Verified after upload:
  installed from PyPI into a clean venv and spot-checked all eight
  0.4.0 behaviours (case folding, the three imaginary spellings, `Q` as
  a plain symbol, `8E3` = 8000, the micro sign, `ex()` refusing TR,
  transient). The published sha256s match the local build byte for
  byte. `requirements.txt`'s `symbulator>=0.4.0` now resolves, so the
  server version can be deployed.
- ~~Publish `symbulator` 0.3.0 to PyPI~~ **DONE 17 Aug 2026** — live at
  https://pypi.org/project/symbulator/ with a CHANGELOG. `pip install
  -r requirements.txt` now resolves normally.
- **Adaptive solve timeout** for restrictive hosts: try the killable
  subprocess, fall back to an in-process timeout where the host forbids
  spawning (some shared cPanel/CloudLinux setups). Needed before cPanel
  is a safe target for the *Flask* version; irrelevant to the browser
  build, which has no server at all.
- **Deploy to Render**, then point `symbulator.perez-franco.com` at it
  (CNAME). Later: migrate to Roberto's cPanel host — `passenger_wsgi.py`
  is already in place for that.
- **Open source**: two repos (`symbulator`, `symbulator-web`), MIT,
  CHANGELOG, CONTRIBUTING, CI running the test suite, `CITATION.cff`,
  optionally Zenodo DOIs and PyPI trusted publishing.
- **Fix the 0 F capacitor bug in the original calculator source** (v7
  and v8) — Roberto is doing this himself; the exact one-line edits are
  in the two PDFs produced earlier. Keep this out of public-facing copy.
- **Refresh the `symbulator-project` skill** once the site is deployed —
  the saved version predates all of the website work.
- **Open-source conversation with Roberto** — he wants Symbulator to
  outlive him. The footer already says it is open source; the actual
  repos, licence headers, governance and archival plan are still to be
  agreed. This is the next conversation, by his own instruction.
