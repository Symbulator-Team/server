#!/usr/bin/env python3
"""Every number the By-Hand Equations card shows obeys the Rounding setting.

#359. The card sends each answer twice: `value`, a plain string, and
`latex`, the typeset copy the page actually renders. `value` went through
the rounding helper from the day the card shipped (#330); `latex` was
built from the exact expression, so a reader with Rounding on 4 digits
was shown `I_1 = 0.0371701871246538 es + 1.0706575835657 js` in the one
box they read, while the answers above the card said `0.03717`.

Roberto found it on the monograph's "One of each" showcase, which is why
that circuit is the fixture here: its mesh solution is six symbolic
answers whose coefficients are long irrational-looking floats, so a
missed rounding is unmissable. A circuit with tidy integer answers would
pass this check while broken -- there would be no digits to drop.

The check drives `byhand_ui` exactly as `/api/byhand` does and asserts
that the digits in `latex` match the digits in `value`, at two different
Rounding settings so a hard-coded 4 cannot pass by luck.

Run standalone (`python tools/check_byhand_rounding.py`) or through
`build_local.py`, which fails the build on a non-zero exit.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)

#: The monograph's "One of each: the 2013 showcase" -- one element of
#: every kind, and a mesh solution in long floats.
CIRCUIT = "\n".join([
    "es,e,0,es",
    "js,0,d,js",
    "r1,e,m,10",
    "r2,a,e,20",
    "r3,m,0,30",
    "r4,b,m,40",
    "r5,n,m,50",
    "r6,c,d,60",
    "r7,n,d,70",
    "jd1,a,b,0.2vr7",
    "ed2,c,b,0.1ir5",
    "jd3,n,c,2ir1",
    "ed4,0,n,0.7vr6",
])

NUMBER = re.compile(r"\d+\.\d+")


def significant(text: str) -> list[int]:
    """The significant-digit count of every decimal in `text`."""
    out = []
    for m in NUMBER.finditer(text):
        digits = m.group(0).replace(".", "").lstrip("0")
        out.append(len(digits))
    return out


def main() -> int:
    sys.path.insert(0, SERVER)
    try:
        import symbulator_ui as ui
    except Exception as exc:                              # noqa: BLE001
        print("check_byhand_rounding: cannot import symbulator_ui: %r" % (exc,))
        return 1

    problems = []
    for digits in (4, 6):
        out = ui.byhand_ui(CIRCUIT, "dc", "", "mesh", digits=digits,
                           si=False, units=False, approx=False)
        methods = (out or {}).get("methods") or {}
        checked = 0
        for name, block in sorted(methods.items()):
            for answer in block.get("answers") or []:
                latex = answer.get("latex") or ""
                value = answer.get("value") or ""
                got, want = significant(latex), significant(value)
                checked += 1
                if got != want:
                    problems.append(
                        "  rounding %d, %s answer %s:\n"
                        "     value: %s\n"
                        "     latex: %s"
                        % (digits, name, answer.get("name"), value, latex))
                for n in got:
                    if n > digits:
                        problems.append(
                            "  rounding %d, %s answer %s: the typeset copy "
                            "carries a %d-digit number\n     latex: %s"
                            % (digits, name, answer.get("name"), n, latex))
        if not checked:
            problems.append("  rounding %d: no answers came back at all -- "
                            "the fixture stopped solving, so this check "
                            "proves nothing" % digits)

    if problems:
        print("check_byhand_rounding: the By-Hand card's typeset answers do "
              "not obey the Rounding setting:")
        print("\n".join(problems))
        return 1
    print("check_byhand_rounding: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
