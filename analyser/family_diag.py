"""Why did the family-table checks fire?  Categories only, no names or numbers.

  python -m analyser.family_diag 4ORL2827 7BWX0040 9QRK8238
"""
import re
import sys

from . import load, match, qr, rules_marriage
from .load import get
from .verify import pehchan, ulb_edisha


def rank(a, b):
    return match.name_match(a, b)


def main():
    wanted = set(sys.argv[1:])
    print("family_diag v5 (categories and masked layouts only)")
    for req, _, _ in load.load_module("marriage"):
        if not req or req.family_id not in wanted:
            continue
        ui = req.user_info
        name, spouse = get(ui, "Name"), get(ui, "Spouse Full Name")
        print(f"\n--- {req.family_id} created {req.request_id.rsplit('_', 1)[-1]}  request type: {req.request_type}  place: {get(ui, 'Place of Marriage') or '-'}")
        print("request-for / whom-to-move:", get(ui, "Request For") or "-", "/", get(ui, "Whom to Move") or "-",
              "  want to add to spouse family:", get(ui, "Want to add to spouse family") or "-")
        for key in ("old_family", "new_family"):
            rows = req.family(key)
            if rows is None:
                print(f"{key}: not captured")
                continue
            ranks = [rank(name, get(r, "Full Name", "Name")) for r in rows]
            best = max(ranks, key=lambda x: ["missing", "none", "partial", "close", "exact"].index(x), default="none")
            hit = rows[ranks.index(best)] if rows else {}
            print(f"{key}: {len(rows)} rows; applicant best match: {best}; "
                  f"columns: {sorted(rows[0].keys()) if rows else '-'}")
            if best in ("exact", "close", "partial"):
                print(f"   matched row: relation={get(hit, 'Relation With HOF') or '-'} gender={get(hit, 'Gender') or '-'} "
                      f"spouse column {'filled' if get(hit, 'Spouse Name') else 'blank'}; "
                      f"PPP spouse vs request spouse: {rank(get(hit, 'Spouse Name'), spouse)}; "
                      f"PPP spouse vs applicant's father: {rank(get(hit, 'Spouse Name'), get(hit, 'Father Name'))}, "
                      f"mother: {rank(get(hit, 'Spouse Name'), get(hit, 'Mother Name'))}, "
                      f"spouse column has digits: {bool(re.search(r'\\d', get(hit, 'Spouse Name')))}")
            else:
                print("   closest other rows' relations:", sorted({get(r, 'Relation With HOF') or '-' for r in rows}))
        link = qr.best_link(qr.decode_pdf(req.pdf_path)) if req.pdf_path else None
        m = re.search(r"https?://[^\s|\"'<>]+", link or "")
        host = qr.classify(link)[1] if m else ""
        if m and (host in rules_marriage.ULB_HOSTS or host in rules_marriage.PEHCHAN_HOSTS):
            verifier = ulb_edisha if host in rules_marriage.ULB_HOSTS else pehchan
            f = verifier.verify(m.group(0)).fields
            print(f"certificate source: {host}; fields parsed: {sorted(f)}")
            for k in ("groom_name", "groom_father", "bride_name", "bride_father"):
                if k in f:
                    shape = re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", f[k]))
                    print(f"   layout {k}: {shape[:60]}{'...' if len(shape) > 60 else ''} ({len(f[k])} chars)")
            print("   request name layout:", re.sub(r"[A-Za-z]", "a", name), "| spouse layout:", re.sub(r"[A-Za-z]", "a", spouse))
            for role in ("bride", "groom"):
                print(f"   {role} name: {len(match.tokens(f.get(role + '_name')))} word(s); applicant vs it: {rank(name, f.get(role + '_name'))}, "
                      f"spouse vs it: {rank(spouse, f.get(role + '_name'))}; request name has {len(match.tokens(name))} word(s), "
                      f"spouse name {len(match.tokens(spouse))} word(s)")
            from difflib import SequenceMatcher
            for role in ("bride", "groom"):
                ta, tb = match.tokens(name), match.tokens(f.get(role + "_name"))
                grid = [[round(SequenceMatcher(None, match.phonetic(x), match.phonetic(y)).ratio(), 2) for y in tb] for x in ta]
                same = [[match._same_word(x, y) for y in tb] for x in ta]
                print(f"   word similarity applicant x {role} (rows applicant words): {grid}; same_word: {same}")
            for role in ("bride", "groom"):
                rf, cf = get(ui, "Father Name"), f.get(role + "_father")
                ta, tb = match.tokens(rf), match.tokens(cf)
                grid = [[round(SequenceMatcher(None, match.phonetic(x), match.phonetic(y)).ratio(), 2) for y in tb] for x in ta]
                print(f"   applicant's request father vs {role}'s father on certificate: {rank(rf, cf)}; words {len(ta)} / {len(tb)}; similarity {grid}")
            for role in ("bride", "groom"):
                print(f"certificate {role}: applicant={rank(name, f.get(role + '_name'))} spouse={rank(spouse, f.get(role + '_name'))}")
            hit = next((r for r in (req.family("old_family") or []) if rank(name, get(r, 'Full Name')) in ("exact", "close", "partial")), None)
            if hit:
                for role in ("bride", "groom"):
                    print(f"   PPP spouse vs certificate {role}: {rank(get(hit, 'Spouse Name'), f.get(role + '_name'))}")
            # the spouse's own row, as rules_marriage looks it up
            for key in ("new_family", "old_family"):
                rows = req.family(key) or []
                best = max(rows, key=lambda r: ["missing", "none", "partial", "close", "exact"].index(rank(spouse, get(r, "Full Name"))), default=None)
                if best is not None and rank(spouse, get(best, "Full Name")) in ("exact", "close", "partial"):
                    for role in ("bride", "groom"):
                        if rank(spouse, f.get(role + "_name")) in ("exact", "close", "partial"):
                            print(f"   spouse row in {key}: relation={get(best, 'Relation With HOF') or '-'} "
                                  f"father vs certificate: {rank(get(best, 'Father Name'), f.get(role + '_father'))} "
                                  f"(tokens PPP {len(match.tokens(get(best, 'Father Name')))} / cert {len(match.tokens(f.get(role + '_father')))}), "
                                  f"mother vs certificate: {rank(get(best, 'Mother Name'), f.get(role + '_mother'))} "
                                  f"(tokens PPP {len(match.tokens(get(best, 'Mother Name')))} / cert {len(match.tokens(f.get(role + '_mother')))})")
                    break


if __name__ == "__main__":
    main()
