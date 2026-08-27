# EqSheet — interactive equation solver (TK!Solver / SolveSys style)

Rule sheet → tick equations → mark variables Known/Unknown → Solve
(SciPy `root`, hybrid Powell; least-squares if the system isn't square).

Mounted on the main app at
`https://symbulator.pythonanywhere.com/eqsheet/` — `eqsheet.py` is the
Blueprint (routes and solver), `templates/eqsheet.html` is the page.
Developed standalone in Aug 2026 and integrated the same month; the
app's **What if…** button (Download Output card, after a DC or
numeric-ω AC solve) opens it preloaded with that solve's equation
system and results via the `?import=` contract below. The offline
builds carry the button too — EqSheet needs SciPy, so it is
server-hosted only, an outward link like Documentation.

## Modes
- **DC · real** — everything is a real number; one value/guess per variable.
- **AC · phasor** — `j` (or `I`) is the imaginary unit. Every equation is
  split into real and imaginary parts (n rules → 2n real equations). Each
  variable is declared **Complex** (2 scalar unknowns), **Real only**, or
  **Imag only** (1 each); values and guesses are entered as Re / Im pairs.
  Results show rectangular and polar (magnitude ∠ degrees) forms.

The balance badge counts scalars: in AC, 3 rules and 3 complex unknowns is
square (6 = 6); a real-only unknown counts once.

## Run locally
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000/eqsheet/

It rides the main app — there is nothing separate to run or deploy. On
PythonAnywhere it arrives with a normal `git pull` + **Reload**, plus
`pip install numpy scipy` the first time (they are in
`requirements.txt`).

## SI prefixes
Every variable row has a prefix dropdown (p n µ m — k M G T). The entered
value or guess is multiplied by that factor: 4 with **m** means 0.004; 2
with **k** means 2000. In AC mode one prefix applies to both Re and Im.
Results are displayed back in the same prefix. Symbulator imports arrive
in base units and get a sensible prefix chosen automatically
(0.004 → 4 m, matching the app's own SI-prefix output style).

## Rule syntax
One equation per line, exactly one `=`. `^` means power. `#` starts a
comment. Available: sin cos tan asin acos atan atan2 sinh cosh tanh exp
log ln log10 sqrt abs min max pi e — plus, in AC: j I conj re im.

## Importing a Symbulator system
The app's **What if…** button does this with one click — the payload is
built at solve time in `symbulator_ui.solve_ui` and travels in the
`?import=` URL. `tools/eqsheet_export.py` is the reference
implementation of the same contract, for doing it from a shell:

    python tools/eqsheet_export.py "e1,1,0,12:r1,1,2,2'k:r2,2,0,1'k"              # DC JSON
    python tools/eqsheet_export.py "e1,1,0,10:r1,1,2,100:l1,2,0,0.1" --domain ac --omega 1000
    python tools/eqsheet_export.py "..." --url https://symbulator.pythonanywhere.com/eqsheet  # link

Paste the JSON into "Import a system", or open the `?import=` link — the
mode switches automatically, equations land in the Rule Sheet, and every
result arrives as a Known (AC values as Re/Im pairs). Untick/flip from
there: drop the source equation, fix a current, solve the source backwards.

## Notes
- Guesses matter: nonlinear systems converge to the root nearest the start.
- Non-square systems are solved least-squares and flagged in the result.
- Residuals (AC: their magnitudes) are shown after each solve.
- Derived Symbulator results (`p_*`, `s_*`, `z_*`, …) import as Knowns too;
  they only appear in the Variable Sheet if a selected rule mentions them.
