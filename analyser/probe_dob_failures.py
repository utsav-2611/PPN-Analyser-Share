"""Why is the requested DOB not found on board / school certificates?  (cached Vision + tesseract text only, no network.)

  python -m analyser.probe_dob_failures
Respects CRID_WORK_ROOT.  For documents of the weaker school types where the requested DOB is not found it prints counts of
what the text does contain (nothing, a date line, dates elsewhere, a Hindi birth label only) and the most common masked
shapes of the lines that carry a date together with the line before them (a shape is printed when >= MIN documents share
it).  No names or numbers.  Saves to store/probe_dob_failures.txt.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import dobtext, load, match, ocr, vision_ocr
from .probe_dob_layout import mask

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_failures.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
GROUPS = ("Matriculation certificate", "Middle School certificate", "School Leaving Certificate", "Senior Secondary certificate")
MIN = 3
DATEISH = re.compile(r"\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\W{0,3}\d{2,4}", re.I)


def main():
    lines = ["probe_dob_failures v1 (counts and masked shapes only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    for group in GROUPS:
        total = failed = 0
        kinds, shapes, years = Counter(), Counter(), Counter()
        for rid, r in sorted(reqs.items()):
            if items.get(rid, {}).get("docType") != group or not r.pdf_path:
                continue
            v = vision_ocr.cached_text(r.pdf_path)
            if v is None:
                continue
            t = (ocr.cached_text(r.pdf_path) or ("", {}))[0]
            both = v + "\n" + t
            total += 1
            new = match.parse_date(r.user_info.get("Requested DOB"))
            if dobtext.find_dob(both, new) == "exact":
                continue
            failed += 1
            dates, ys = dobtext.dob_context(both)
            words = len(re.findall(r"\w+", v))
            kinds["almost no text (<30 words)" if words < 30 else
                  "date on a birth line" if dates else
                  "year only on a birth line" if ys else
                  "dates elsewhere only" if dobtext.dates_in(both) else
                  "Hindi birth label, no date" if "जन्म" in both else "no date at all"] += 1
            years["requested year present anywhere" if new and str(new.year) in re.sub(r"\s", "", both) else "requested year absent"] += 1
            seen = set()
            vl = v.splitlines()
            for i, line in enumerate(vl):
                if DATEISH.search(line):
                    seen.add(" // ".join(mask(x) for x in (vl[i - 1] if i else "", line)))
            for sh in seen:
                shapes[sh] += 1
        lines.append(f"\n=== {group}: {total} read, requested DOB not found in {failed} ===")
        lines.append("   " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
        lines.append("   " + ", ".join(f"{k} {v}" for k, v in years.most_common()))
        lines.append(f"   most common (previous line // date line) shapes in those documents (>= {MIN}):")
        for sh, c in shapes.most_common(14):
            if c >= MIN:
                lines.append(f"      x{c}  {sh[:130]}")
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
