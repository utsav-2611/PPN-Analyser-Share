"""Would other ways of writing a date find the requested DOB where it is now not found?  (cached text only, no network.)

  python -m analyser.probe_dob_forms
Respects CRID_WORK_ROOT.  For board / school certificates where the requested DOB is not found it counts, per document type,
how many would be found by each looser reading: two digit year, year first (ISO), spaces only between day month year, eight
digits run together, OCR letter-for-digit slips (O 0, l 1, S 5, B 8), and day / month / year spread over nearby lines.
Counts only.  Saves to store/probe_dob_forms.txt.
"""
import json
import re
from collections import Counter
from pathlib import Path

from . import dobtext, load, match, ocr, vision_ocr

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_forms.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
GROUPS = ("Matriculation certificate", "Middle School certificate", "School Leaving Certificate", "Senior Secondary certificate")


def forms(text, d):
    """{form name: True} for each looser reading that finds date d in text."""
    dd, mm, yyyy, yy = f"{d.day:02d}", f"{d.month:02d}", f"{d.year}", f"{d.year % 100:02d}"
    sep = r"\s*[/.\-]\s*"
    flat = text.translate(dobtext.DEV_DIGITS)
    out = {}
    out["two digit year"] = bool(re.search(rf"(?<!\d)0?{int(dd)}{sep}0?{int(mm)}{sep}{yy}(?!\d)", flat))
    out["year first"] = bool(re.search(rf"(?<!\d){yyyy}{sep}0?{int(mm)}{sep}0?{int(dd)}(?!\d)", flat))
    out["spaces only"] = bool(re.search(rf"(?<!\d)0?{int(dd)}\s+0?{int(mm)}\s+{yyyy}(?!\d)", flat))
    out["eight digits"] = bool(re.search(rf"(?<!\d){dd}{mm}{yyyy}(?!\d)", flat))
    fixed = flat.translate(str.maketrans("OoIl|SB", "0011158"))
    out["letter for digit"] = dobtext.find_dob(fixed, d) == "exact"
    lines = [x for x in flat.splitlines() if x.strip()]
    hit = False
    for i in range(len(lines)):
        window = " ".join(lines[i:i + 4])
        if re.search(rf"(?<!\d)0?{int(dd)}(?!\d)", window) and re.search(yyyy, window) and \
                re.search(dobtext.MONTHS[d.month - 1][:3], window, re.I):
            hit = True
            break
    out["spread over lines"] = hit
    return out


def main():
    lines = ["probe_dob_forms v1 (counts only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    for group in GROUPS:
        failed, kinds, any_form = 0, Counter(), 0
        for rid, r in sorted(reqs.items()):
            if items.get(rid, {}).get("docType") != group or not r.pdf_path:
                continue
            v = vision_ocr.cached_text(r.pdf_path)
            if v is None:
                continue
            both = v + "\n" + (ocr.cached_text(r.pdf_path) or ("", {}))[0]
            new = match.parse_date(r.user_info.get("Requested DOB"))
            if not new or dobtext.find_dob(both, new) == "exact":
                continue
            failed += 1
            f = forms(both, new)
            kinds.update(k for k, ok in f.items() if ok)
            any_form += any(f.values())
        lines.append(f"{group}: not found {failed}, found by some looser form {any_form}: " +
                     (", ".join(f"{k} {v}" for k, v in kinds.most_common()) or "none"))
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
