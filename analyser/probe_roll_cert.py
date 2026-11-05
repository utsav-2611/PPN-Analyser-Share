"""How does the electoral roll certificate print the age?  (cached Vision text only, no network.)

  python -m analyser.probe_roll_cert
Respects CRID_WORK_ROOT.  For the electoral roll certificates it counts how many have each kind of age statement and prints the
commonest masked shapes (label words kept, other words a, digits 9) of lines that mention age or birth, each with the next line.
A shape is printed when at least 2 certificates share it.  Saves to store/probe_roll_cert.txt.
"""
import json
import re
from collections import Counter
from pathlib import Path

from . import dobtext, load, vision_ocr
from .probe_dob_layout import mask

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_roll_cert.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"


def main():
    lines = ["probe_roll_cert v3 (counts and masked shapes only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    kinds, shapes, dshapes = Counter(), Counter(), Counter()
    n = 0
    samples = []
    for rid, r in sorted(reqs.items()):
        if items.get(rid, {}).get("docType") != "Electoral roll certificate" or not r.pdf_path:
            continue
        text = vision_ocr.cached_text(r.pdf_path)
        if text is None:
            continue
        n += 1
        kinds["plain age parsed"] += bool(dobtext.plain_ages(text))
        kinds["age as on parsed"] += bool(dobtext.ages_as_on(text))
        kinds["word 'age' present"] += bool(re.search(r"\bage\b", text, re.I))
        kinds["word 'birth' present"] += bool(re.search(r"birth", text, re.I))
        kinds["a date present"] += bool(dobtext.dates_in(text))
        kinds["Devanagari present"] += bool(re.search(r"[\u0900-\u097f]", text))
        kinds["word 'electoral' present"] += bool(re.search(r"electoral|election", text, re.I))
        vl = text.splitlines()
        if len(samples) < 3 and not dobtext.plain_ages(text) and not dobtext.ages_as_on(text):
            samples.append([mask(x) for x in vl if x.strip()][:45])
        seen = set()
        dseen = set()
        for i, line in enumerate(vl):
            if dobtext.dates_in(line) or re.search(r"(?<!\d)\d{2}(?!\d)", line):
                dseen.add(" // ".join(mask(x) for x in (vl[i - 1] if i else "", line)))
        dshapes.update(dseen)
        for i, line in enumerate(vl):
            if re.search(r"\bage\b|birth", line, re.I):
                seen.add(" // ".join(mask(x) for x in (line, vl[i + 1] if i + 1 < len(vl) else "")))
        shapes.update(seen)
    lines.append(f"electoral roll certificates read: {n}")
    lines.append("   " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    lines.append("   commonest (age or birth line // next line) shapes, >= 2:")
    for sh, c in shapes.most_common(25):
        if c >= 2:
            lines.append(f"      x{c}  {sh[:140]}")
    lines.append("   commonest (previous line // line with a date or a two digit number) shapes, >= 3:")
    for sh, c in dshapes.most_common(30):
        if c >= 3:
            lines.append(f"      x{c}  {sh[:140]}")
    for k, sample in enumerate(samples, 1):
        lines.append(f"   --- masked lines of certificate {k} (first 45) ---")
        lines.extend("      " + x[:100] for x in sample)
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
