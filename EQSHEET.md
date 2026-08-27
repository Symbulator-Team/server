# The Numerical Solver (TK!Solver / SolveSys style)

List of Equations → tick equations → mark variables Known/Unknown →
Solve (SciPy `root`, hybrid Powell; least-squares if the system isn't
square). **EqSheet** was its working name, and the URL and file names
keep it as the internal handle; everything a user sees says
Numerical Solver (#118).

Mounted on the main app at
`https://symbulator.pythonanywhere.com/eqsheet/` — `eqsheet.py` is the
Blueprint (routes and solver), `templates/eqsheet.html` is the page.
Developed standalone in Aug 2026 and integrated the same month; the
app's **Numerical Solver** button (the Explore numerically card, active
after a DC or numeric-ω AC solve) opens it preloaded with that solve's
equation system and results via the `?import=` contract below. The
offline builds carry the button too — the solver needs SciPy, so it is
server-hosted only, an outward link like Documentation.

## Modes
- **DC · real** — everything is a real number; one value/guess per variable.
- **AC · phasor** — `j` (or `I`) is the imaginary unit. Every equation is
  split into real and imaginary parts (n equations → 2n real equations).
  Each variable is declared **Complex** (2 scalar unknowns), **Real
  only**, or **Imag only** (1 each); values and guesses are entered as
  Re / Im pairs. Results show rectangular and polar (magnitude ∠
  degrees) forms.

The balance badge counts scalars: in AC, 3 equations and 3 complex
unknowns is square (6 = 6); a real-only unknown counts once.

The page has a dark mode, sharing the app's toggle mechanism and its
`symbulator-theme` storage key — the two pages are same-origin, so one
choice carries to both.

## Run locally
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000/eqsheet/

It rides the main app — there is nothing separate to run or deploy. On
PythonAnywhere it arrives with a normal `git pull` + **Reload**, plus
`pip install numpy scipy` the first time (they are in
`requirements.txt`).

## SI prefixes
Every variable row has a prefix dropdown (p n µ m — blank — k M G T; the
blank entry means no prefix). The entered value or guess is multiplied
by that factor: 4 with **m** means 0.004; 2 with **k** means 2000. In AC
mode one prefix applies to both Re and Im. Results are displayed back in
the same prefix. Symbulator imports arrive in base units and get a
sensible prefix chosen automatically (0.004 → 4 m, matching the app's
own SI-prefix output style).

## Equation syntax
One equation per line, exactly one `=`. `^` means power. `#` starts a
comment. Available: sin cos tan asin acos atan atan2 sinh cosh tanh exp
log ln log10 sqrt abs min max pi e — plus, in AC: j I conj re im.

## Importing a Symbulator system
The app's **Numerical Solver** button does this with one click — the
payload is built at solve time in `symbulator_ui.solve_ui` and travels
in the `?import=` URL. When a very large circuit would push the URL past
what the host accepts (~8 KB request line), the button saves the same
JSON as `numerical_system.json` instead and the page's **Open a system
file…** button reads it back — which also makes a system keepable and
re-openable later. `tools/eqsheet_export.py` is the reference
implementation of the contract, for doing it from a shell:

    python tools/eqsheet_export.py "e1,1,0,12:r1,1,2,2'k:r2,2,0,1'k"              # DC JSON
    python tools/eqsheet_export.py "e1,1,0,10:r1,1,2,100:l1,2,0,0.1" --domain ac --omega 1000
    python tools/eqsheet_export.py "..." --url https://symbulator.pythonanywhere.com/eqsheet  # link

On import the mode switches automatically, the equations land in the
List of Equations (all ticked), and every variable arrives **Unknown**
with its solved value as the guess — the sheet lands square and
re-solves as it stands. Flip variables to Known as you pin them down:
drop the source equation, fix a current, solve the source backwards.

## Notes
- Every new variable — imported or typed by hand — starts Unknown.
- A Known variable's Result shows its given value immediately.
- Guesses matter: nonlinear systems converge to the root nearest the start.
- Non-square systems are solved least-squares and flagged in the result.
- Residuals (AC: their magnitudes) are shown after each solve, raw.
- Displayed results are chopped for numerical noise per variable type:
  within each name-prefix group (`v…`, `i…`, …), anything 1e8 times
  smaller than the group's largest magnitude shows as 0, as does
  anything below 1e-18 outright. Display only — the residuals line and
  the solver's numbers are untouched.
- Derived Symbulator results (`p_*`, `s_*`, `z_*`, …) import too; they
  only appear in the Variable sheet if a selected equation mentions them.
