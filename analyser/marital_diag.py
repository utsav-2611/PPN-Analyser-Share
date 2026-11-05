"""Why did the Marital name / father checks fire?  Numbers and categories only: no names.

  python -m analyser.marital_diag
Uses cached official-site records only (it never opens a site), so it runs in seconds.
"""
import os
from collections import Counter
from difflib import SequenceMatcher

os.environ["PPN_CACHE_ONLY"] = "1"

from . import load, match, rules_marital
from .load import get


def grid(a, b):
    ta, tb = match.tokens(a), match.tokens(b)
    return [[round(SequenceMatcher(None, match.phonetic(x), match.phonetic(y)).ratio(), 2) for y in tb] for x in ta]


def main():
    print("marital_diag v2 (numbers and categories only)")
    seen = Counter()
    for req, _, _ in load.load_module("marital"):
        if not req or load.norm(req.request_type) not in ("widow", "widower"):
            continue
        captured = {}
        orig = rules_marital._compare

        def spy(r, rec, kind, name, done, facts, _o=orig):
            captured["rec"] = rec
            return _o(r, rec, kind, name, done, facts)

        rules_marital._compare = spy
        try:
            d = rules_marital.analyse(req)
        finally:
            rules_marital._compare = orig
        want = [f for f in d.flags if f in ("Father differs", "Deceased differs", "Different spouse")]
        if not want or "rec" not in captured:
            continue
        c, ui = captured["rec"].fields, req.user_info
        sp, spf, me, myf = get(ui, "Spouse Full Name"), get(ui, "Spouse Father Name"), get(ui, "Name") or req.name, get(ui, "Father Name")
        seen[want[0]] += 1
        print(f"\n--- {req.family_id} {want[0]} via {captured['rec'].source}")
        if want[0] == "Different spouse":
            cs = c.get("spouse")
            print(f"   applicant vs certificate spouse: {match.name_match(me, cs)}; words {len(match.tokens(me))}/{len(match.tokens(cs))}; grid {grid(me, cs)}")
            print(f"   certificate spouse vs: applicant's father {match.name_match(cs, myf)}, deceased (request) {match.name_match(cs, sp)}, "
                  f"certificate father {match.name_match(cs, c.get('father'))}, certificate mother {match.name_match(cs, c.get('mother'))}")
            print(f"   deceased (request) vs certificate name: {match.name_match(sp, c.get('name'))}; date of death agrees: {c.get('dod') == (match.parse_date(get(ui, 'Date Of Death')) or '').isoformat() if match.parse_date(get(ui, 'Date Of Death')) else 'n/a'}")
            continue
        print(f"   deceased name: request {len(match.tokens(sp))} word(s) vs certificate {len(match.tokens(c.get('name')))}: "
              f"{match.name_match(sp, c.get('name'))}; grid {grid(sp, c.get('name'))}")
        print(f"   spouse father (request) vs certificate father: {match.name_match(spf, c.get('father'))}; words {len(match.tokens(spf))}/{len(match.tokens(c.get('father')))}; grid {grid(spf, c.get('father'))}")
        print(f"   spouse father (request) vs certificate MOTHER: {match.name_match(spf, c.get('mother'))};"
              f" vs APPLICANT's own father (request): {match.name_match(spf, myf)}; applicant's father vs certificate father: {match.name_match(myf, c.get('father'))}")
        print(f"   spouse name column used the father's name? request spouse vs request spouse father: {match.name_match(sp, spf)}; "
              f"certificate has father {bool(c.get('father'))} mother {bool(c.get('mother'))} spouse {bool(c.get('spouse'))}")
    print("\nsummary:", dict(seen))


if __name__ == "__main__":
    main()
