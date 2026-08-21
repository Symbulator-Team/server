# Deploying Symbulator Web

The app is a plain WSGI (Flask) application, so the same code runs
without changes wherever it's hosted -- only the entry-point wiring
differs. **It's currently live on PythonAnywhere** (see below); Render
and cPanel were the original plan and are documented further down in
case of a future migration, but PythonAnywhere is where deploys
actually happen today.

## Files

- `app.py` -- the whole backend (routes, validation, solver subprocess with timeout)
- `examples.sym` -- **the examples dropdown.** Plain text, edit freely;
  the server re-reads it on every page load, so no restart is needed.
  The file's own header comment documents the format. If it's missing or
  unparseable the site still runs, just without examples.
- `circuitbook.py` -- parser/formatter for that same format, shared by
  the examples file and by user uploads
- `templates/index.html` -- the whole frontend (one page)
- `static/mathjax/tex-svg.js` -- MathJax, served locally so the math
  rendering has no third-party CDN dependency (and the page even falls
  back to plain-text results if the script somehow fails to load)
- `requirements.txt` -- Flask, gunicorn, and the `symbulator` package from PyPI
- `render.yaml` -- Render configuration (used automatically when the repo is connected)
- `passenger_wsgi.py` -- entry point for cPanel/PythonAnywhere; harmless on Render

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
   new code or packages without an explicit reload. Either click Reload
   on the "Web" tab for `Symbulator.pythonanywhere.com`, or from a
   console: `touch /var/www/symbulator_pythonanywhere_com_wsgi.py`
   (equivalent; either works).
5. **Verify by actually using the live site** -- load
   `symbulator.pythonanywhere.com` and run a real solve. Don't stop at
   "the pull/reload command didn't error"; that doesn't catch a
   version-mismatch crash, which only shows up on an actual request.

Free-tier PythonAnywhere caveat: the account needs a login at least once
a month (a "Run until 1 month from today" button on the Web tab) or the
site gets disabled -- there's no traffic-based keep-alive like Render's.

## Originally planned, not currently used: Render.com (free tier)

1. Put this folder in a GitHub repository (public or private).
2. On https://render.com: New + -> Web Service -> connect the repo.
   Render reads `render.yaml` and fills everything in; just click deploy.
3. First deploy takes a few minutes (installing SymPy). You get a URL
   like `https://symbulator.onrender.com`.
4. Custom domain: in the service's Settings -> Custom Domains, add
   `symbulator.perez-franco.com`; Render shows you a CNAME record to
   create at your DNS provider (wherever perez-franco.com's DNS lives,
   likely your cPanel host). HTTPS certificates are automatic.

Free-tier caveat: the service spins down after ~15 min idle; the first
visit after that takes ~30-60 s to wake. Fine for sharing with
colleagues/students; upgrade or migrate when it matters.

## Originally planned, not currently used: your cPanel host

1. cPanel -> "Setup Python App" -> Create application.
   - Python version: 3.9+ (the newest offered)
   - Application root: e.g. `symbulator_web` (upload this folder there)
   - Application URL: the subdomain you created (symbulator.perez-franco.com)
   - Application startup file: `passenger_wsgi.py` (usually the default)
2. In the app's virtualenv (cPanel shows the command, something like
   `source /home/USER/virtualenv/symbulator_web/3.x/bin/activate`):
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
