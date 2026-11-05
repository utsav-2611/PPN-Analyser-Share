"""How the reference recommendations relate to the request data (DOB module).

  python -m analyser.probe_dob_reference
Respects CRID_WORK_ROOT and ELECTORS_DB.  Counts and common phrases only: a phrase is printed only when at least
MIN different requests share it, digits are masked, so names and numbers cannot appear.  Saves to store/probe_dob_reference.txt.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import electors, load, match

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_reference.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
MIN = 15


def gap(ppp, req):
    if not ppp or not req:
        return "unparsed"
    if ppp == req:
        return "same date"
    y = abs(ppp.year - req.year)
    side = "older" if req < ppp else "younger"
    return f"{side} {'same year' if y == 0 else '1y' if y == 1 else '2y' if y == 2 else '3-5y' if y <= 5 else '6-10y' if y <= 10 else '>10y'}"


def phrases(texts, n=4):
    seen = defaultdict(set)
    for i, t in enumerate(texts):
        words = re.sub(r"\d+", "9", re.sub(r"[^\w\s]", " ", str(t))).split()
        for j in range(len(words) - n + 1):
            seen[" ".join(words[j:j + n])].add(i)
    return [(p, len(s)) for p, s in sorted(seen.items(), key=lambda kv: -len(kv[1])) if len(s) >= MIN]


def table(title, rows, lines):
    lines.append(f"\n{title}")
    keys = sorted({k for _, k in rows})
    by = defaultdict(Counter)
    for rec, k in rows:
        by[k][rec] += 1
    for k in keys:
        c = by[k]
        lines.append(f"   {k}: " + ", ".join(f"{r} {c[r]}" for r in ("APPROVE", "REJECT", "HOLD") if c[r]))


def main():
    lines = ["probe_dob_reference v1 (counts only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = json.loads(REF.read_text(encoding="utf-8"))["items"]
    ref = {str(it["requestId"]): it for it in items}
    joined = [(ref[i], reqs[i]) for i in reqs if i in ref]
    lines.append(f"requests {len(reqs)}   reference {len(ref)}   joined {len(joined)}")

    table("recommendation by reference docType", [(it["recommendation"], it["docType"]) for it, _ in joined], lines)
    table("recommendation by uploaded document (request label)",
          [(it["recommendation"], r.user_info.get("Uploaded Document", "")) for it, r in joined], lines)
    table("recommendation by tab", [(it["recommendation"], r.tab) for it, r in joined], lines)
    table("recommendation by DOB change",
          [(it["recommendation"], gap(match.parse_date(r.user_info.get("DOB In PPP")), match.parse_date(r.user_info.get("Requested DOB"))))
           for it, r in joined], lines)
    for doc in sorted({it["docType"] for it, _ in joined}):
        sub = [(it["recommendation"], gap(match.parse_date(r.user_info.get("DOB In PPP")), match.parse_date(r.user_info.get("Requested DOB"))))
               for it, r in joined if it["docType"] == doc]
        if len(sub) >= 15:
            table(f"[{doc}] recommendation by DOB change", sub, lines)

    # voter card: EPIC lookup in the roll
    lines.append("\n--- voter card lookup (Uploaded Document starts with 'Voter ID') ---")
    rows_found, rows_fit, matched_form = [], [], Counter()
    as_on_seen = Counter()
    for it, r in joined:
        if not str(r.user_info.get("Uploaded Document", "")).startswith("Voter ID"):
            continue
        epic = r.user_info.get("Document Number", "")
        found = electors.lookup(epic)
        found = [f for f in found if not f.get("deleted")] or found
        rows_found.append((it["recommendation"], "found" if found else "not found" if re.search(r"\d", epic) else "no usable number"))
        if found:
            f = found[0]
            as_on = match.parse_date(f.get("age_as_on"))
            as_on_seen[str(f.get("age_as_on"))[:2] and re.sub(r"\d", "9", str(f.get("age_as_on")))] += 1
            req = match.parse_date(r.user_info.get("Requested DOB"))
            ppp = match.parse_date(r.user_info.get("DOB In PPP"))
            if as_on and req and f.get("age") is not None:
                rows_fit.append((it["recommendation"],
                                 f"requested {'fits' if match.dob_fits_age(req, int(f['age']), as_on) else 'outside'} roll age; "
                                 f"PPP {'fits' if ppp and match.dob_fits_age(ppp, int(f['age']), as_on) else 'outside'}"))
            matched_form["same as typed" if f.get("matched_epic") == electors.normalize_epic(epic) else "zero variant"] += 1
            matched_form["deleted in roll" if f.get("deleted") else "not deleted"] += 1
    table("lookup result", rows_found, lines)
    table("roll age vs DOBs", rows_fit, lines)
    lines.append(f"match form: {dict(matched_form)}   age_as_on shapes: {dict(as_on_seen)}")
    lines.append(f"names in requests containing Devanagari: {sum(1 for _, r in joined if re.search(chr(0x900) + '-' + chr(0x97F), r.name) or any(0x900 <= ord(c) <= 0x97F for c in r.name))}")

    for rec in ("REJECT", "HOLD", "APPROVE"):
        for field in ("proposedRemark", "notes", "analysis"):
            texts = [it.get(field, "") for it, _ in joined if it["recommendation"] == rec and it.get(field)]
            lines.append(f"\n--- {rec} {field}: common 4-word phrases (in >= {MIN} requests; {len(texts)} texts) ---")
            for p, n in phrases(texts)[:25]:
                lines.append(f"   x{n}  {p}")

    text = "\n".join(lines)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
