#!/usr/bin/env python3
"""An author `display` beats the browser's own [hidden] { display: none }.

Setting `display` on an element in the stylesheet silently disables its
`hidden` attribute, whatever the specificity -- the UA rule and the author
rule are in different cascade origins and the author always wins. So
`el.hidden = true` sets the attribute, the DOM property reads back true,
and the element goes on rendering.

That has now bitten this app three times:

  .solution-pick   an empty picker under the Outputs heading before a run
  label.checkline  #242's "Show image" tick on entries with no picture
  #rtab            an empty EQUATION/VARIABLES header on a blank eqsheet

The first two were found by eye, months apart. The third had been live
for as long as the Numerical Solver has, and nobody had reported it.
The trap is that the obvious check is wrong: `el.hidden` reads the
property, which is true, so an automated audit of the DOM says the
element is hidden while the screen shows it.

This checks the static form of it: for every element the page ever hides,
every stylesheet rule that sets a `display` on that element must be
accompanied by a `[hidden]` rule turning it off again.

Run:  py tools/check_hidden_guards.py
Prove it works:  delete a `[hidden]` line and watch it go red.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
TEMPLATES = ('templates/index.html', 'templates/eqsheet.html')


def hidden_elements(s):
    """ids the page hides: `hidden` in the markup, or `.hidden =` in JS."""
    ids = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)\.hidden\s*=", s))
    ids |= set(re.findall(r"getElementById\('([A-Za-z0-9_]+)'\)\.hidden\s*=", s))
    # <tag id="x" ... hidden> in the markup
    for m in re.finditer(r'<[a-z]+\b[^>]*>', s, re.I):
        tag = m.group(0)
        if re.search(r'\bhidden\b(?!-)(?![\w-]*\s*=)', tag):
            i = re.search(r'\bid="([A-Za-z0-9_]+)"', tag)
            if i:
                ids.add(i.group(1))
    return ids


def element_targets(s, eid):
    """The selectors that name this element: its id and each of its classes."""
    m = re.search(r'<[a-z]+\b[^>]*\bid="%s"[^>]*>' % re.escape(eid), s, re.I)
    if not m:
        return []
    out = ['#' + eid]
    c = re.search(r'\bclass="([^"]*)"', m.group(0))
    if c:
        out += ['.' + n for n in c.group(1).split() if n]
    return out


def rules(s):
    """(selector, body) for every rule in every <style> block."""
    out = []
    for block in re.findall(r'(?is)<style[^>]*>(.*?)</style>', s):
        block = re.sub(r'(?s)/\*.*?\*/', ' ', block)
        for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', block):
            out.append((m.group(1).strip(), m.group(2)))
    return out


def rightmost(sel):
    """The last compound in a selector -- what the rule actually targets.

    `.setnote .hint:last-child` targets `.hint`, not `.setnote`; without
    this the child's rule is blamed on the parent and the check cries wolf.
    """
    part = re.split(r'[\s>+~]+', sel.strip())[-1]
    return set(re.findall(r'[#.][A-Za-z0-9_-]+', part))


def check(path):
    s = io.open(path, encoding='utf-8').read()
    all_rules = rules(s)
    guarded = set()
    for sel, _ in all_rules:
        if '[hidden]' not in sel:
            continue
        for one in sel.split(','):
            if '[hidden]' in one:
                guarded |= rightmost(one.replace('[hidden]', ''))

    bad = []
    for eid in sorted(hidden_elements(s)):
        targets = set(element_targets(s, eid))
        if not targets:
            continue
        for sel, body in all_rules:
            if '[hidden]' in sel:
                continue
            d = re.search(r'(?:^|;)\s*display\s*:\s*([a-z-]+)', body)
            if not d or d.group(1) == 'none':
                continue
            for one in sel.split(','):
                hit = rightmost(one) & targets
                if hit and not (hit & guarded):
                    bad.append((eid, one.strip(), d.group(1)))
    return bad


def main():
    findings = 0
    for rel in TEMPLATES:
        path = os.path.join(SERVER, rel)
        if not os.path.exists(path):
            print('MISSING: %s' % path)
            return 2
        bad = check(path)
        findings += len(bad)
        print('%-24s %s' % (rel, 'ok' if not bad else '%d FINDING(S)' % len(bad)))
        for eid, sel, disp in bad:
            print('   #%s is hidden somewhere, but `%s` sets display: %s'
                  % (eid, sel, disp))
            print('      -> add  %s[hidden] { display: none; }' % sel)
    if findings:
        print('\nAn author display beats [hidden]; the element renders anyway.')
        return 1
    print('\nEvery hideable element with a display rule has its [hidden] guard.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
