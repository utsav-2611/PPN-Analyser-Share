"""Do other resolutions or rotations let Vision find the requested DOB in documents where it was missed?

  python -m analyser.probe_vision_variants
Respects CRID_WORK_ROOT.  Takes the board / school certificates and SLCs where the cached Vision + tesseract text does not
contain the requested DOB, re-reads each with Apple Vision at 200 and 450 dpi and turned 90, 180 and 270 degrees, and counts how
many now show it.  Local only; prints counts.  Texts are cached in store/cache/ocr_variants/ (a second run is instant).
Saves to store/probe_vision_variants.txt.
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from . import dobtext, load, match, ocr, vision_ocr

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_vision_variants.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
GROUPS = ("Matriculation certificate", "Middle School certificate", "School Leaving Certificate", "Senior Secondary certificate")
VARIANTS = vision_ocr.VARIANTS
MAX_SIDE = 5000


variant_text = vision_ocr.variant_text


def main():
    lines = ["probe_vision_variants v1 (counts only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    todo = []
    for rid, r in sorted(reqs.items()):
        if items.get(rid, {}).get("docType") in GROUPS and r.pdf_path:
            v = vision_ocr.cached_text(r.pdf_path)
            t = (ocr.cached_text(r.pdf_path) or ("", {}))[0]
            if v is not None and dobtext.find_dob(v + "\n" + t, match.parse_date(r.user_info.get("Requested DOB"))) != "exact":
                todo.append((items[rid]["docType"], r, v + "\n" + t))
    lines.append(f"documents where the requested DOB was not found: {len(todo)}")
    res = {g: Counter() for g in GROUPS}
    n = Counter()
    for i, (group, r, base) in enumerate(todo, 1):
        print(f"   {i}/{len(todo)}", file=sys.stderr)
        n[group] += 1
        new = match.parse_date(r.user_info.get("Requested DOB"))
        won = set()
        for name, dpi, angle in VARIANTS:
            try:
                text = variant_text(r.pdf_path, name, dpi, angle)
            except Exception as e:
                res[group]["failed " + type(e).__name__] += 1
                continue
            if dobtext.find_dob(base + "\n" + text, new) == "exact":
                res[group][name] += 1
                won.add(name)
            res[group][name + " words>=30"] += len(re.findall(r"\w+", text)) >= 30
        res[group]["any variant finds it"] += bool(won)
        res[group]["only one variant"] += len(won) == 1
    for g in GROUPS:
        lines.append(f"\n=== {g}: {n[g]} documents ===")
        lines.append("   " + ", ".join(f"{k} {v}" for k, v in sorted(res[g].items())))
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
