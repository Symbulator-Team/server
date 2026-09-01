"""
The Flask half of the Numerical Solver: the Blueprint the main app
mounts at /eqsheet/, and nothing else.

It exists because eqsheet.py does not import Flask any more (#208,
31 Aug 2026). The Solver now runs in the offline builds too, where
Pyodide imports that module inside the browser tab and there is no
server to speak HTTP to, so the parsing and the solving had to stop
being route handlers. What was a Blueprint decorator is three lines of
wrapping here; repos/local/bridge.py wraps the same two functions the
other way, in JSON.

Keep this file thin. Anything with an opinion about the mathematics
belongs in eqsheet.py, where both front ends can reach it -- a check
added here alone would guard the hosted Solver and leave the
downloaded one without it.
"""

from flask import Blueprint, request, jsonify, render_template

import eqsheet

bp = Blueprint("eqsheet", __name__, url_prefix="/eqsheet")


@bp.post("/api/parse")
def api_parse():
    return jsonify(eqsheet.api_parse(request.get_json(force=True)))


@bp.post("/api/solve")
def api_solve():
    return jsonify(eqsheet.api_solve(request.get_json(force=True)))


@bp.get("/")
def index():
    return render_template("eqsheet.html")
