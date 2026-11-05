"""Categories and relationships in the DOB requests, plus the structure of the Palwal reference file.

  python -m analyser.probe_dob_values
Respects CRID_WORK_ROOT.  Prints counts only: a value is shown only when at least MIN requests share it,
otherwise it is counted as 'other'.  Names, numbers and free text are never printed.  Saves to store/probe_dob_values.txt.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import load, match, qr

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_values.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
MIN = 10


def shown(counter):
    big = {k: v for k, v in counter.items() if v >= MIN}
    other = sum(v for k, v in counter.items() if v < MIN)
    s = ", ".join(f"{k!r} x{v}" for k, v in sorted(big.items(), key=lambda kv: -kv[1]))
    return s + (f", other x{other}" if other else "")


def year_gap(a, b):
    if not a or not b:
        return "unparsed"
    y = abs(a.year - b.year)
    return "0" if y == 0 else "1" if y == 1 else "2" if y == 2 else "3 to 5" if y <= 5 else "6 to 10" if y <= 10 else "over 10"


def reference_report(lines):
    lines.append("\n--- reference file structure ---")
    if not REF.exists():
        lines.append("reference/palwal_dob_recommendations.json NOT FOUND")
        return
    data = json.loads(REF.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("items") or data.get("recommendations") or list(data.values())
    lines.append(f"top level: {type(data).__name__}" + (f" keys {list(data)[:12]}" if isinstance(data, dict) else ""))
    if isinstance(data, dict) and not isinstance(items, list):
        items = list(data.values())
    lines.append(f"entries: {len(items)}")
    keys = Counter(k for it in items if isinstance(it, dict) for k in it)
    lines.append(f"entry keys: {dict(keys)}")
    for k in keys:
        vals = Counter(str(it.get(k)) if not isinstance(it.get(k), (dict, list)) else f"<{type(it.get(k)).__name__}>"
                       for it in items if isinstance(it, dict))
        if len(vals) <= 12:
            lines.append(f"   {k}: {dict(vals)}")
        else:
            lines.append(f"   {k}: {len(vals)} distinct, e.g. shapes {dict(Counter(qr.shape(v) for v in vals).most_common(3))}")
    ids = [str(it.get("id") or it.get("requestId") or "") for it in items if isinstance(it, dict)]
    lines.append(f"id shapes: {dict(Counter(qr.shape(i) for i in ids).most_common(4))}")


def main():
    lines = ["probe_dob_values v1 (counts only)", f"work root: {load.WORK_ROOT}"]
    reqs = [r for r, _, _ in load.load_module("dob") if r]
    lines.append(f"requests: {len(reqs)}")

    doc = Counter(str(r.user_info.get("Uploaded Document", "")).strip() for r in reqs)
    lines.append(f"\nUploaded Document: {shown(doc)}")
    for status_key in ("Status", "Reason"):
        c = Counter(str(b.get(status_key, "")).strip() for r in reqs for _, _, b in r.subordinate_remarks())
        lines.append(f"remark {status_key}: {shown(c)}")
    lines.append(f"by tab: {dict(Counter(r.tab for r in reqs))}")
    lines.append(f"module None -> tab: {dict(Counter(r.tab for r in reqs if not r.raw.get('module')))}")
    lines.append(f"Ticket Closer present -> tab: {dict(Counter(r.tab for r in reqs if 'Ticket Closer' in r.case))}")

    lines.append("\n--- Document Number shape by Uploaded Document ---")
    by_doc = defaultdict(Counter)
    for r in reqs:
        by_doc[str(r.user_info.get('Uploaded Document', '')).strip()][qr.shape(str(r.user_info.get("Document Number", "")))] += 1
    for d, c in sorted(by_doc.items(), key=lambda kv: -sum(kv[1].values())):
        if sum(c.values()) >= MIN:
            lines.append(f"   {d!r}: {dict(c.most_common(6))}")
    letters_only = Counter(str(r.user_info.get("Document Number", "")).strip().lower()[:20] for r in reqs
                           if re.fullmatch(r"[^\W\d_ ]+( [^\W\d_]+)*", str(r.user_info.get("Document Number", "")).strip()))
    lines.append(f"letters-only Document Number values: {shown(letters_only)}")
    lines.append(f"Document Number length (chars) buckets: {dict(Counter(len(str(r.user_info.get('Document Number', ''))) // 5 * 5 for r in reqs))}")

    lines.append("\n--- dates ---")
    fmt = Counter()
    gaps, direction, ppp_default = Counter(), Counter(), Counter()
    for r in reqs:
        ppp_raw, req_raw = r.user_info.get("DOB In PPP", ""), r.user_info.get("Requested DOB", "")
        fmt[qr.shape(str(req_raw))] += 1
        ppp, req = match.parse_date(ppp_raw), match.parse_date(req_raw)
        gaps[year_gap(ppp, req)] += 1
        if ppp and req:
            direction["requested earlier (older)" if req < ppp else "requested later (younger)" if req > ppp else "same"] += 1
            ppp_default["PPP 01 01" if (ppp.day, ppp.month) == (1, 1) else "other"] += 1
    lines.append(f"Requested DOB shape: {dict(fmt)}   parsed by match.parse_date: {sum(1 for r in reqs if match.parse_date(r.user_info.get('Requested DOB', '')))}")
    lines.append(f"year gap PPP vs requested: {dict(gaps)}")
    lines.append(f"direction: {dict(direction)}")
    lines.append(f"PPP DOB on 1 January: {dict(ppp_default)}")
    ages = Counter()
    for r in reqs:
        d = match.parse_date(r.user_info.get("Requested DOB", ""))
        ages[(2026 - d.year) // 10 * 10 if d else -1] += 1
    lines.append(f"requested age decade today (-1 = unparsed): {dict(sorted(ages.items()))}")

    lines.append("\n--- family table and applicant ---")
    in_fam, rel, blanks = Counter(), Counter(), Counter()
    for r in reqs:
        rows = r.family() or []
        me = [row for row in rows if match.name_match(row.get("Full Name", row.get("FULL NAME", "")), r.name) in ("exact", "close")]
        in_fam["applicant found in family" if me else "not found"] += 1
        for row in me[:1]:
            rel[str(row.get("Relation With HOF", row.get("RELATION WITH HOF", ""))).strip().upper()] += 1
            fam_dob = match.parse_date(row.get("Date of Birth", row.get("DATE OF BIRTH", "")))
            blanks["family row DOB equals 'DOB In PPP'" if fam_dob == match.parse_date(r.user_info.get("DOB In PPP", "")) else "differs"] += 1
    lines.append(f"{dict(in_fam)}")
    lines.append(f"applicant relation with HOF: {shown(rel)}")
    lines.append(f"family-row DOB vs DOB In PPP: {dict(blanks)}")
    lines.append(f"Spouse Name blank: {sum(1 for r in reqs if not str(r.user_info.get('Spouse Name', '')).strip())}   "
                 f"Mother blank: {sum(1 for r in reqs if not str(r.user_info.get('Mother Name', '')).strip())}")

    reference_report(lines)
    text = "\n".join(lines)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
