"""What does the Hindi text look like where the requested DOB is not found?  (cached text only, no network.)

  python -m analyser.probe_dob_hindi
Respects CRID_WORK_ROOT.  Apple Vision reads English only, so Hindi lines come from the cached tesseract (eng+hin) text, which is
already combined with the Vision text.  For documents where the requested DOB is not found it counts how many contain
Devanagari, a Hindi birth label, Devanagari digits, Hindi month names, Hindi words for numbers, and prints the commonest masked
shapes (digits 9, other words a) of the birth-label lines with the line after them.  Counts only.  Saves to store/probe_dob_hindi.txt.
"""
import json
import re
from collections import Counter
from pathlib import Path

from . import dobtext, load, match, ocr, vision_ocr
from .probe_dob_layout import mask

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_hindi.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
GROUPS = ("Matriculation certificate", "Middle School certificate", "School Leaving Certificate", "Senior Secondary certificate", "Voter ID")
HI_MONTHS = ("जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "सितम्बर", "अक्टूबर", "नवंबर", "नवम्बर", "दिसंबर", "दिसम्बर")
LABEL = re.compile(r"जन्म|जनम")


def main():
    lines = ["probe_dob_hindi v1 (counts and masked shapes only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    for group in GROUPS:
        failed, kinds, shapes = 0, Counter(), Counter()
        for rid, r in sorted(reqs.items()):
            if items.get(rid, {}).get("docType") != group or not r.pdf_path:
                continue
            v = vision_ocr.cached_text(r.pdf_path)
            if v is None:
                continue
            t = (ocr.cached_text(r.pdf_path) or ("", {}))[0]
            both = v + "\n" + t
            new = match.parse_date(r.user_info.get("Requested DOB"))
            if not new or dobtext.find_dob(both, new) == "exact":
                continue
            failed += 1
            kinds["Devanagari present"] += bool(re.search(r"[ऀ-ॿ]", t))
            kinds["Hindi birth label"] += bool(LABEL.search(t))
            kinds["Devanagari digits"] += bool(re.search(r"[०-९]", t))
            kinds["Hindi month name"] += any(m in t for m in HI_MONTHS)
            kinds["tesseract text empty"] += not t.strip()
            tl = t.splitlines()
            seen = set()
            for i, line in enumerate(tl):
                if LABEL.search(line):
                    seen.add(" // ".join(mask(x) for x in (line, tl[i + 1] if i + 1 < len(tl) else "")))
            shapes.update(seen)
        lines.append(f"\n=== {group}: requested DOB not found in {failed} ===")
        lines.append("   " + (", ".join(f"{k} {n}" for k, n in kinds.most_common()) or "none"))
        for sh, c in shapes.most_common(12):
            if c >= 2:
                lines.append(f"      x{c}  {sh[:130]}")
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
