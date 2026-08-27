"""Run every entry of a lesson's input file through the real app, and print
what the reader would see beside what the chapter prints.

The earlier version of this script read `values` from the response. That is
the exact substitution dictionary the Evaluate card is fed -- it ignores the
Rounding and SI settings entirely, so an entry with the wrong rounding looked
identical to one with the right rounding and every check passed. What the
reader sees is `nodes` and `elements`, whose `plain` strings are already
rounded, prefixed and given units. Those are what this compares now.

    py verify_lesson.py Lesson_03
    py verify_lesson.py Lesson_03 --only 13
    py verify_lesson.py Lesson_03 --quiet      # only entries that disagree
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)        # tools/ lives inside repos/server
sys.path.insert(0, SERVER)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import circuitbook                                            # noqa: E402
import app as flask_app                                       # noqa: E402


def rounding_args(c):
    r = str(c.get("rounding") or "exact")
    if r == "exact":
        return {"digits": 0, "approx": False}
    if r == "approx":
        return {"digits": 0, "approx": True}
    try:
        return {"digits": int(r), "approx": True}
    except ValueError:
        return {"digits": 0, "approx": False}


def shown_answers(r):
    """{answer name: the string the page shows}, exactly as displayed."""
    out = {}
    for nd in r.get("nodes") or []:
        out["v" + str(nd.get("node", ""))] = nd.get("plain", "")
    for el in r.get("elements") or []:
        name = el.get("name", "")
        for item in el.get("items") or []:
            out[str(item.get("sym", "")) + name] = item.get("plain", "")
    for ex in r.get("extras") or []:
        if ex.get("name"):
            out[ex["name"]] = ex.get("plain", "")
    return out


def names_in(text):
    """The answer names a book line mentions, longest first so `ir10` is not
    read as `ir1` followed by a stray 0."""
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
    return sorted(toks, key=len, reverse=True)


def main():
    name = sys.argv[1]
    only = None
    if "--only" in sys.argv:
        only = int(sys.argv[sys.argv.index("--only") + 1])
    quiet = "--quiet" in sys.argv

    expected = {}
    exp_path = os.path.join(HERE, name + ".expected.json")
    if os.path.exists(exp_path):
        expected = json.load(io.open(exp_path, encoding="utf-8"))

    path = os.path.join(SERVER, "examples", name + ".cir")
    text = io.open(path, encoding="utf-8").read()
    circuits, warnings, title = circuitbook.parse_book(text)
    print(f"{name}: {title!r}, {len(circuits)} entries")
    for w in warnings or []:
        print("  parse warning:", w)

    c = flask_app.app.test_client()
    bad, unchecked = [], []
    for n, e in enumerate(circuits, 1):
        if only and n != only:
            continue
        payload = {
            "desc": e["desc"],
            "domain": e.get("domain", "dc"),
            "omega": e.get("omega", ""),
            "tool": e.get("tool") or "solve",
            "n1": e.get("n1", ""), "n2": e.get("n2", ""),
            "kind": e.get("kind", "z"),
            "si": bool(e.get("si")), "units": bool(e.get("units", True)),
            "use_rms": bool(e.get("rms")), "polar": bool(e.get("polar")),
            "equations": e.get("equations", []),
            "unknowns": e.get("unknowns", ""),
            "conditions": e.get("conditions", []),
            "variables": ([v.strip() for v in str(e.get("vars", "")).split(",")
                           if v.strip()] or None),
        }
        payload.update(rounding_args(e))
        r = c.post("/api/solve", json=payload).get_json()

        book = expected.get(e["name"], "")
        lines = [f"\n[{n}] {e['name']}"]
        if not r.get("ok"):
            bad.append((n, e["name"], r.get("error")))
            lines.append(f"   ** DOES NOT SOLVE: {r.get('error')}")
            print("\n".join(lines))
            continue

        vals = r.get("values") or {}
        shown = shown_answers(r)
        if book:
            lines.append(f"   book: {book}")
            pick, seen = [], set()
            for tok in names_in(book):
                if tok in shown and tok not in seen:
                    seen.add(tok)
                    pick.append(f"{tok}={shown[tok]}")
            lines.append("   app:  " + (", ".join(pick) if pick
                                        else "(no matching names)"))
            if not pick:
                unchecked.append((n, e["name"]))
        else:
            keys = sorted(shown)[:8]
            lines.append("   app:  " + ", ".join(f"{k}={shown[k]}"
                                                 for k in keys))

        ra = rounding_args(e)
        if e.get("evaluate"):
            rr = c.post("/api/evaluate",
                        json={"expr": e["evaluate"], "values": vals,
                              "domain": e.get("domain", "dc"),
                              "conditions": e.get("evaluate_conditions", []),
                              **ra, "si": bool(e.get("si")),
                              "units": bool(e.get("units", True))}).get_json()
            got = rr.get("plain") or rr.get("error")
            lines.append(f"   evaluate {e['evaluate']!r} -> {got}")
            if not rr.get("ok"):
                bad.append((n, e["name"], f"evaluate: {rr.get('error')}"))

        if e.get("solve_equations"):
            rr = c.post("/api/solveq",
                        json={"equations": e["solve_equations"],
                              "unknowns": e.get("solve_unknowns", ""),
                              "conditions": e.get("solve_conditions", []),
                              "values": vals,
                              "domain": e.get("domain", "dc"),
                              "units": bool(e.get("units", True)),
                              "real_only": bool(e.get("solve_real_only")),
                              **ra}).get_json()
            sols = rr.get("solutions") or []
            if not sols:
                bad.append((n, e["name"], "solve equations found nothing"))
                lines.append("   ** SOLVE EQUATIONS FOUND NOTHING: "
                             f"{rr.get('error') or rr.get('notes')}")
            for s in sols[:2]:
                lines.append("   solve -> " + "; ".join(
                    f"{x['name']}={x['plain']}" for x in s))

        problem = any("**" in ln for ln in lines)
        if not quiet or problem:
            print("\n".join(lines))
        sys.stdout.flush()

    print(f"\n{len(bad)} entr(ies) with a problem")
    for n, nm, why in bad:
        print(f"   [{n}] {nm}: {why}")
    if unchecked:
        print(f"{len(unchecked)} entr(ies) whose book names were not found "
              f"among the answers:")
        for n, nm in unchecked:
            print(f"   [{n}] {nm}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
