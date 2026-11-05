"""Why does a Married request say 'PPP already shows a different spouse'?  Numbers and categories only.

  python -m analyser.married_diag
Uses the cached certificate (ULB / eDisha / Pehchan); opens no site that is not already cached.
"""
from difflib import SequenceMatcher

from . import load, match, rules_marital, rules_marriage
from .load import get


def grid(a, b):
    ta, tb = match.tokens(a), match.tokens(b)
    return [[round(SequenceMatcher(None, match.phonetic(x), match.phonetic(y)).ratio(), 2) for y in tb] for x in ta]


def main():
    print("married_diag v1 (numbers and categories only)")
    for req, _, _ in load.load_module("marital"):
        if not req or load.norm(req.request_type) != "married":
            continue
        got = {}
        orig = rules_marriage._compare

        def spy(r, rec, ui, name, facts, conclusion="", _o=orig):
            got.update(rec=rec, ui=ui, req=r)
            return _o(r, rec, ui, name, facts, conclusion)

        rules_marriage._compare = spy
        try:
            d = rules_marital.analyse(req)
        finally:
            rules_marriage._compare = orig
        print(f"\n--- {req.family_id}: {d.recommendation} {','.join(d.flags) or '-'}")
        if "rec" not in got:
            continue
        cert, ui = got["rec"].fields, got["ui"]
        name, spouse = get(ui, "Name"), get(ui, "Spouse Full Name")
        rows = got["req"].family("old_family") or []
        row = next((r for r in rows if match.name_match(name, get(r, "Full Name")) in ("exact", "close", "partial")), None)
        ppp = get(row, "Spouse Name") if row else ""
        party = "bride" if match.acceptable(name, cert.get("bride_name")) else "groom" if match.acceptable(name, cert.get("groom_name")) else "?"
        other = cert.get("groom_name" if party == "bride" else "bride_name")
        print(f"   applicant is {party}; request status {get(ui, 'Current Status In PPP')} -> {get(ui, 'Requested Status In PPP')}")
        print(f"   PPP spouse column: {'filled' if ppp else 'blank'}; PPP spouse vs request spouse: {match.name_match(ppp, spouse)}; "
              f"PPP spouse vs certificate other party: {match.name_match(ppp, other)} grid {grid(ppp, other)}")
        print(f"   request spouse vs certificate other party: {match.name_match(spouse, other)}; words {len(match.tokens(spouse))}/{len(match.tokens(other))}")
        print(f"   PPP spouse vs applicant's own father: {match.name_match(ppp, get(ui, 'Father Name'))}, mother: {match.name_match(ppp, get(ui, 'Mother Name'))}")


if __name__ == "__main__":
    main()
