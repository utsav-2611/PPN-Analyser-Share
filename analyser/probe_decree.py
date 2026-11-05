"""How do the divorce decrees read?  Categories and Family IDs only: no names, numbers or decree text.

  python -m analyser.probe_decree
The first run OCRs every decree (a few minutes); results are cached.
"""
import re
from collections import Counter

from . import decree, load, match, ocr, rules_divorce
from .load import get

SAFE = {"yes", "no", "true", "false", "wife", "husband", "mother", "father", "self", "spouse", "child", "children", "merge",
        "outmigration", "both", "none", "haryana", "outsideharyana", "bride", "groom", "male", "female"}


def shape(value):
    v = str(value or "").strip()
    if not v:
        return "(blank)"
    if v.lower() in SAFE:
        return v
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", v))[:30]


def children_rows(req):
    rows = []
    for key in ("old_family", "new_family", "family"):
        rows += req.family(key) or []
    return sum(1 for r in rows if re.search(r"son|daughter|child", load.norm(get(r, "Relation With HOF")))) 


def main():
    print("probe_decree v3 (categories and Family IDs only)")
    field_counts = {k: Counter() for k in ("Request For", "Whom to Move", "Is Children Also Moved", "Want to Add Parent Family",
                                           "Want to add to spouse family", "Name of Court", "Case No", "Date of Divorce")}
    unknown_words = []
    table, kinds, custody_states, scripts, methods = [], Counter(), Counter(), Counter(), Counter()
    for module in ("marriage", "marital"):
        for req, _, _ in load.load_module(module):
            if not req or load.norm(req.request_type) != "divorced":
                continue
            ui = req.user_info
            for k, c in field_counts.items():
                if get(ui, k) != "" or k in ("Request For", "Whom to Move", "Is Children Also Moved"):
                    c[shape(get(ui, k))] += 1
            if not req.pdf_path:
                table.append((req.family_id, module, "no pdf"))
                continue
            text, info = ocr.text_of(req.pdf_path)
            kind, sig = decree.classify(text)
            name, spouse, spouse_src, genders = rules_divorce.parties(req)
            a, s = decree.find_party(name, text), decree.find_party(spouse, text)
            cu = decree.custody(text)
            side = decree.resolve_custody(cu, {"applicant": a[1], "spouse": s[1]}, genders)
            verdict = rules_divorce.analyse(req) if module == "marriage" else None
            low = text.lower()
            unknown_words.append((req.family_id + (" [unknown type]" if kind == "unknown" else ""),
                                  {w: low.count(w) for w in ("first motion", "second motion", "six months", "dissolved", "decree",
                                                             "granted", "allowed", "judgment", "order", "petition", "compromise",
                                                             "settlement", "annexure", "appeal", "statement", "withdraw")},
                                  {w: low[:700].count(w) for w in ("decree", "judgment", "order", "petition", "appeal")}))
            asked = match.parse_date(get(ui, "Date of Divorce", "Date of Court Order"))
            found = decree.dates_in(text)
            court = decree.court_found(get(ui, "Name of Court", "Court Name"), text)
            kinds[kind] += 1
            custody_states[cu["state"] + (":" + cu["who"] if cu["who"] else "")] += 1
            scripts[sig["script"]] += 1
            methods[info["method"]] += 1
            table.append((req.family_id, module, f"pages {info['pages']} {info['method']} {sig['script']} words {sig['words']}",
                          f"kind {kind} (grant {sig.get('grant', '-')} act {int(bool(sig.get('act')))} court {int(bool(sig.get('court')))} "
                          f"crim {sig.get('criminal', '-')} agr {sig.get('agreement', '-')} app {sig.get('appeal', '-')})",
                          f"applicant {a[0]}/{a[1] or '-'} spouse({spouse_src}) {s[0]}/{s[1] or '-'} petition {decree.petition_kind(text) or '-'}",
                          f"custody {cu['state']}/{cu['who'] or '-'} -> {side or '-'}; children rows in family {children_rows(req)}",
                          f"request date {'found' if asked in found else 'absent' if asked else 'none'}; court {court}",
                          f"RULES: {verdict.recommendation} {','.join(verdict.flags) or '-'}" if verdict else "RULES: (marital rules later)"))
    print("\nrequest fields (shapes; words shown only when plain):")
    for k, c in field_counts.items():
        print(f"  {k}: {dict(c)}")
    print("\ndocument kind:", dict(kinds))
    print("custody:", dict(custody_states))
    print("script:", dict(scripts), " text source:", dict(methods))
    if unknown_words:
        print("\nkeyword counts per document (whole text | first 700 characters):")
        for fid, counts, head in unknown_words:
            print(f"  {fid}: {counts} | {head}")
    print("\nper request (Family ID | module | ...):")
    for row in table:
        print("  " + " | ".join(str(x) for x in row))


if __name__ == "__main__":
    main()
