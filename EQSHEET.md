# The Numerical Solver (TK!Solver / SolveSys style)

List of Equations → tick equations → mark variables Known/Unknown →
Solve (SciPy `root`, hybrid Powell; least-squares if the system isn't
square). **EqSheet** was its working name, and the URL and file names
keep it as the internal handle; everything a user sees says
Numerical Solver (#118).

Mounted on the main app at
`https://symbulator.pythonanywhere.com/eqsheet/` — and, since **#208**
(31 Aug 2026), in the two offline builds as well, at `eqsheet.html`
beside the app.

`eqsheet.py` is the parsing and the solving and **imports no web
framework**: its two entry points, `api_parse(data)` and
`api_solve(data)`, take a plain dict and return one.
`eqsheet_web.py` is the Flask Blueprint the server mounts on top of
them; `repos/local/eqbridge.py` is the same wrapping in JSON, for
Pyodide in the tab. `templates/eqsheet.html` is the page, and
`build_local.py` generates the offline copy of it by replacing the
body of one function — `post()` — because those two calls are
everything the page asks the server for.

**Do not import flask here.** It would break the offline build at
boot, silently, in a build that never passes through Jinja and so is
green in every check the server has.

The offline Solver needs SciPy, which is why the ZIP is about 30 MB
rather than 17.8. See #208 in `repos/local/NEXT.md`.
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
log ln log10 sqrt abs min max pi e — plus, in AC: j I conj re im — plus,
in DC only, `u(...)`: the unit step (u(0) = 1), for systems handed over
from a transient solve. `u` only acts as the step when it is *called*;
a plain variable named `u` still works.

## Restricting where the solver looks (#131)
Every unknown's row carries a **Restriction** menu: *Unrestricted*
(the default), *Positive*, *Negative*, or *Range…* with a from/to
pair read in the row's SI prefix, like the guess. **One end of a range
may be left empty since #391**, and means open on that side — "3 and
upwards". The solve API has taken a null end since this feature was
built; it was only the page that insisted on both, which left a
condition like `x > 3` nowhere to land. Both ends empty is still a
refusal.

The menu sits in the **last column** since #391 (it used to come between
Status and the value), and its range boxes are the size of an ordinary
value box rather than the small ones they were — there is room at the
end of the row, and there was not in the middle of it.

### Conditions arrive as restrictions (#391)

Expert Mode's **Conditions** are a filter on the solve, not part of the
system, so they have never crossed as equations — an early version sent
them and they arrived as parse errors, `is > 0` being no equation at all.
They cross as **restrictions** instead: `vs > 0` sets Positive on `vs`,
and `vs > 3` with `vs < 7` sets a range from 3 to 7.

Bounds on one name are **combined**, which is the only way a range can
arise, because the chained spelling is refused by the app itself: 
`_parse_inequality` splits on the first operator it finds, so `7 > x > 3`
reaches the value parser as `x > 3` and is rejected as "not arithmetic".
Two conditions is how a reader writes a range today. The tightest lower
bound wins and the lowest upper bound wins; a contradictory pair is
dropped rather than handed over as an empty range.

`> 0` and `< 0` are read as bounds like any other and only become the
sign restrictions when nothing has bounded the other side, so `x > 0`
with `x < 7` arrives as the range it is rather than as Positive with the
7 discarded.

What does not cross, and is left unrestricted rather than approximated:
a condition whose sides are not a bare name and a real number
(`2*vs > 3`, `vs > ir1`), and an `=` condition, which is a substitution.

**DC only.** A restriction is a statement about one real scalar, and
every imported AC variable arrives Complex, where the menu is greyed out;
the only way to make one bite would be to set the variable Real only,
which asserts its imaginary part is zero — a claim about the circuit, not
about where to search.

The payload field is `restrictions`: `{name: "pos" | "neg" | [lo, hi]}`
in **base units**, either end of a range null for open. The page converts
each end into the row's own SI prefix, which is why it applies them after
`results` — the prefix is chosen from the imported value, and applying
them first would put every range out by that factor, silently. A restricted solve
runs through SciPy's `least_squares` with bounds instead of MINPACK's
hybr (which takes none); a square restricted system is judged by its
residual, so a system whose root lies outside the restriction says
"no solution found under the restrictions" rather than presenting a
boundary minimum as an answer. A guess outside its restriction is
moved to an interior starting point — never onto the boundary, where
the trust-region method stalls. In AC the menu applies to Real only /
Imag only unknowns and greys out on Complex ones: a restriction is a
statement about one real scalar, and a complex value has no sign.

Any identifier is a valid variable name, Python keywords included:
`is` — the natural name for a source current — works, as do `in`, `if`
and the rest. They are shielded from Python's parser behind sentinel
names, the same cure the solver applied in 0.5.19; the page only ever
sees the plain names. (`True`, `False` and `None` stay refused: those
are literals.)

## Importing a Symbulator system
The app's **Numerical Solver** button does this with one click — the
payload is built at solve time in `symbulator_ui.solve_ui` and travels
in the `?import=` URL. When a very large circuit would push the URL past
what the host accepts (~8 KB request line), the button saves the same
JSON as `numerical_system.json` instead and the page's **Open a system
file…** button reads it back — which also makes a system keepable and
re-openable later.

All four domains cross now (#124), each in the shape that survives:

- **DC**, and **AC with a numeric ω** — the stamped equation system,
  as always.
- **FD** — the same stamped system (it is algebraic in s), in complex
  mode, with `s` arriving as a **Known** complex variable (j by
  default). Move `s` around the plane and re-solve.
- **TR** — the system is differential and cannot cross, so the
  *answers* cross instead: one equation per solved expression
  (`v2 = 1 - exp(-t)`), with `t` arriving **Known** at 0. Set `t` and
  read every waveform at that instant — or flip an answer to Known and
  `t` to Unknown and the sheet finds *when* the waveform gets there.
  An answer containing `delta(t)` has no numeric value and is left out
  by name in a `#` comment. (With solver 0.5.14 this cannot yet occur:
  impulse-valued TR answers come back from the solver as their
  s-domain constant, not as `DiracDelta` — the Results card shows the
  same.) Only an AC solve with symbolic ω, or a TR solve whose every
  answer carried a delta, produces no payload.

## The third level, and the tick that carries it (#391)

A DC or AC solve works out more than the stamped system holds. After the
KCL system is solved, `analysis._derived` computes a **third level**: each
element's branch voltage `v_<el>` and power `p_<el>` (in AC, the complex
power `s_<el>` and its real part, under `p_` with RMS phasors and `ap_`
without), and — sources only — the resistance or impedance `r_`/`z_<el>`
the source sees looking into the rest of the circuit.

Those values have always crossed, in `results`. What did not cross was
anything **tying them to the circuit**, so they appeared in the Variable
sheet only when some other equation happened to name one. The app's
Numerical Solver card now carries a tick, *Include the derived answers*,
off by default; with it on, the button adds their defining equations to
the ones it hands over.

**They arrive in the List of Equations switched off** (Roberto, 11 Sep
2026), where the stamped system arrives on. So a handover with the tick
on lands exactly where one without it lands — square, on the circuit
alone — and the reader ticks the one line they came for, which is one
more equation and one more unknown, square again. Until a line is ticked
its variable is not in the Variable sheet at all, which is the same rule
derived results have always followed here.

That is what the `unticked` field in the payload is for; see below.

What that buys is the direction the stamped system cannot go: untick the
source's own equation, flip a power to **Known**, and the sheet finds the
source value that delivers it. On `e1,1,0,12:r1,1,2,2'k:r2,2,0,1'k`,
pinning `pr2` at 36 mW returns `v1 = 18 V`.

They are written in the system's **own** first- and second-level
variables — node voltages and branch currents — never in each other, so
any subset of the block stands on its own:

    ve1 = v1
    pe1 = ie1*v1
    -ie1*re1 = v1            # not re1 = v1/(-ie1): a zero current would
    vr1 = v1 - v2            # otherwise put a division into the system
    pr1 = ir1*(v1 - v2)

In AC they use `conj` and `re`, which that mode's namespace has:

    se1 = v1*conj(ie1)/2
    ape1 = re(v1*conj(ie1))/2

**Two payload fields, and only one of them is this page's.**
`third_level` is the app's own: the button merges it into `equations`
when the tick is on and **deletes the key before encoding**, so this page
never sees it. `unticked` *is* this page's, and is the one thing #391
added to the `?import=` contract: **indices into `equations`** whose
lines arrive switched off. Indices rather than a count, so the field says
nothing about where in the list they sit, and rather than the equations'
text, because two elements of one circuit can produce the same line. A
payload without the field behaves exactly as before — everything ticked.

The tick is read at click time, not at solve time, so changing your mind
about it costs no re-solve. A saved `numerical_system.json` carries
`unticked` like the link does, so dropping the file arrives the same way.

The field is absent for TR (its answers cross, not a system) and empty
for FD (`_derived` runs for dc and ac only). The tick hides itself when
there is nothing to offer.

Most of those formulas come from `engine._derived_definition`, which is
where they are written once. It refuses the three AC powers, because
`conjugate` cannot go into a symbolic stamp the linear solver then has to
invert — this page has no such problem, it evaluates to complex and
splits the residual. So those three are written a second time, in
`symbulator_ui.third_level_equations`, and
`tools/check_third_level_export.py` is what stops the two drifting: it
runs the exported equations through `api_parse` and `api_solve` and
compares the sheet's answers with the solver's own. `build_local.py` runs
it on every build.

The optional payload field carrying this is `known`:
`{"t": 0.0}` (real) or `{"s": [0.0, 1.0]}` (complex, [re, im]) — those
variables arrive **Known** at that value; everything else keeps the
arrive-Unknown behaviour below. `tools/eqsheet_export.py` is the
reference implementation of the contract, for doing it from a shell:

    python tools/eqsheet_export.py "e1,1,0,12:r1,1,2,2'k:r2,2,0,1'k"              # DC JSON
    python tools/eqsheet_export.py "e1,1,0,10:r1,1,2,100:l1,2,0,0.1" --domain ac --omega 1000
    python tools/eqsheet_export.py "..." --url https://symbulator.pythonanywhere.com/eqsheet  # link

On import the mode switches automatically, the equations land in the
List of Equations (all ticked, bar any the payload's `unticked` names —
see the third-level section above), and every variable arrives **Unknown**
with its solved value as the guess, **rounded to whatever the app's own
Rounding setting said at the moment the button was pushed** (#391) — at
"exact" it is not rounded, as before. The rounding is the app's own
`_round_expr`, so the sheet cannot disagree with the Results card; note
that it rounds the *number*, not the display, since the sheet's own
Rounding menu is display-only and a variable flipped to Known constrains
the system with whatever value it holds — the sheet lands square and
re-solves as it stands. Flip variables to Known as you pin them down:
drop the source equation, fix a current, solve the source backwards.

The payload uses **sans-underscore names**: the app's `v_1` and `i_r1`
arrive as `v1` and `ir1`, in the equations and the result keys alike
(Roberto's call, 27 Aug 2026). The noise chop groups variables by their
first letter accordingly.

## Notes
- Every new variable — imported or typed by hand — starts Unknown with a
  guess of 0, and an empty guess field is read as 0 when Solve is pressed.
- A Known variable's Result shows its given value immediately.
- A solved variable with no prefix chosen gets the most suitable one
  picked in its own menu (0.004 shows as 4 m); changing a row's prefix
  re-displays its result in the new prefix rather than clearing it.
- Results carry a guessed unit from the variable's first letter — v and
  e are volts, i and j amperes, p watts, r and z ohms, s VA, c farads,
  l henries, g siemens — shown after the prefix, as in `4 mA`.
  Ambiguous letters (t could be time or temperature) guess nothing.
- **Interactive Mode**, a checkbox beside Solve: unchecked, the sheet
  solves only on the button, as always; checked, it tries to solve half
  a second after any change settles — a value typed, a status flipped,
  an equation edited or ticked — so the results track the inputs.
- Guesses matter: nonlinear systems converge to the root nearest the start.
- Non-square systems are solved least-squares and flagged in the result.
- Residuals (AC: their magnitudes) are shown after each solve, raw.
- Displayed results are chopped for numerical noise per variable type:
  within each first-letter group (`v…`, `i…`, …), anything 1e8 times
  smaller than the group's largest magnitude shows as 0, as does
  anything below 1e-18 outright. Display only — the residuals line and
  the solver's numbers are untouched.
- Derived Symbulator results (`pr1`, `se`, `ze`, …) import too; they
  only appear in the Variable sheet if a selected equation mentions them.
