# Deploying Symbulator (server version)

The app is a plain WSGI (Flask) application, so the same code runs
without changes wherever it's hosted -- only the entry-point wiring
differs. **It's currently live on PythonAnywhere** (see below); cPanel
was the original plan and is documented further down in case of a
future migration, but PythonAnywhere is where deploys actually happen
today.

## Files

- `app.py` -- the whole backend (routes, validation, solver subprocess with timeout)
- `examples.cir` -- **the examples dropdown.** Plain text, edit freely;
  the server re-reads it on every page load, so no restart is needed.
  The file's own header comment documents the format. If it's missing or
  unparseable the site still runs, just without examples.
- `circuitbook.py` -- parser/formatter for that same format, shared by
  the examples file and by user uploads
- `templates/index.html` -- the whole frontend (one page)
- `static/mathjax/tex-svg.js` -- MathJax, served locally so the math
  rendering has no third-party CDN dependency (and the page even falls
  back to plain-text results if the script somehow fails to load)
- `requirements.txt` -- Flask and the `symbulator` package from PyPI
- `passenger_wsgi.py` -- entry point for cPanel/PythonAnywhere

## Live now: PythonAnywhere (symbulator.pythonanywhere.com)

The live site is a git clone of this repo at `~/symbulator_web` in the
`Symbulator` PythonAnywhere account, run through a `symbulator-venv`
virtualenv, with the web app wired up via PythonAnywhere's "Web" tab
(WSGI entry point: `passenger_wsgi.py`-style wiring, configured once in
that tab rather than a file you edit here).

To deploy a change:

1. Push the change to this repo first (`main` branch).
2. In a PythonAnywhere Bash console for the `Symbulator` account:

       cd ~/symbulator_web
       source ~/.virtualenvs/symbulator-venv/bin/activate
       git pull

3. **Check whether the new code needs a newer `symbulator` than what's
   installed** before assuming you're done -- `requirements.txt` pins a
   loose lower bound (`symbulator>=0.4.2`), which does *not* force an
   upgrade if the already-installed version already satisfies it. If in
   doubt:

       pip install --upgrade symbulator

   Skipping this when the new code needs a newer package version
   deploys code that will error on every request until someone notices.
4. **Reload the web app** -- PythonAnywhere's WSGI apps do not pick up
   new code or packages without an explicit reload.

   Prefer the **Reload button on the "Web" tab** for
   `Symbulator.pythonanywhere.com`. It is the only option that tells you
   it worked: it shows a spinner and then confirms.

   Touching the WSGI file from a console works too, but look up its real
   name first rather than typing one from memory -- it is derived from
   the domain, and guessing it wrong fails in a way that is easy to miss:

       ls /var/www/

   Then `touch` whatever `*_wsgi.py` that lists. Note that **`touch`
   prints nothing on success** -- silence is the good outcome, and the
   only feedback you get is an error if the path was wrong. That makes
   it indistinguishable from a typo unless you read carefully, which is
   why the button is the better habit.
5. **Check `/healthz` before anything else.** It reports what is really
   deployed, and answers the reload question directly:

       {"ok": true,
        "build": "2026-08-22 11:08 UTC",
        "build_on_disk": "2026-08-22 11:08 UTC",
        "needs_reload": false,
        "solver": "0.4.6"}

   `build` is the footer stamp the running process started with;
   `build_on_disk` is what the files say now. **If they differ,
   `needs_reload` is true and the pull has not reached the process** --
   go back to step 4 and use the Reload button. This is worth knowing
   because the symptom is otherwise baffling: on 22 Aug 2026 a deploy
   served the new page while the API still answered from the previous
   `app.py`, with `git pull` done and `git status` clean. A browser hard
   refresh does not fix it; only a reload does. `solver` is the version
   of the `symbulator` package the process has loaded, which is the other
   half of step 3.

6. **Then verify by actually using the live site** -- load
   `symbulator.pythonanywhere.com` and run a real solve. Don't stop at
   "the pull/reload command didn't error"; that doesn't catch a
   version-mismatch crash, which only shows up on an actual request.

Free-tier PythonAnywhere caveat: the account needs a login at least once
a month (a "Run until 1 month from today" button on the Web tab) or the
site gets disabled -- there's no traffic-based keep-alive.

## Originally planned, not currently used: your cPanel host

1. cPanel -> "Setup Python App" -> Create application.
   - Python version: 3.9+ (the newest offered)
   - Application root: e.g. `symbulator_server` (upload this folder there)
   - Application URL: the subdomain you created (symbulator.perez-franco.com)
   - Application startup file: `passenger_wsgi.py` (usually the default)
2. In the app's virtualenv (cPanel shows the command, something like
   `source /home/USER/virtualenv/symbulator_server/3.x/bin/activate`):
   `pip install -r requirements.txt`
3. Restart the app from the cPanel page. Done -- same code, zero edits.

Note: a few shared hosts restrict spawning subprocesses. The solver
uses a child process for its timeout guard; if your host blocks it,
solves will fail immediately rather than hang -- if that happens, ask
the host about `multiprocessing`, or we can switch the guard to a
thread + interrupt strategy.

## Knobs

- `SYMBULATOR_TIMEOUT` (env var, seconds, default 25): hard kill time
  for a single solve.
- If the site ever gets real traffic, add rate limiting (e.g.
  `flask-limiter`) -- not included yet because a hobby deployment
  doesn't need it and it adds a dependency.

## Local run (for testing on your own machine)

    pip install -r requirements.txt
    python app.py
    # then open http://localhost:5000
