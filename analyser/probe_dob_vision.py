"""Read every DOB document with Apple Vision (cached) and report how often the requested DOB is found, per type.

  python -m analyser.probe_dob_vision
Respects CRID_WORK_ROOT.  Local only.  Counts and masked sample lines only (same masking as probe_dob_layout).
Saves to store/probe_dob_vision.txt.  The first run reads about 1000 documents (roughly 1 s each); later runs are instant.
"""
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import dobtext, electors, load, match, ocr, vision_ocr
from .probe_dob_layout import mask

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_vision.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
KEYWORD = re.compile(r"birth|dob|d\.o\.b|\bage\b|years|dated|issued|epic|elector|year", re.I)
SAMPLES, LINES = 3, 12


def main():
    if not vision_ocr.available():
        print("Apple Vision is not available in this Python (pip install pyobjc-framework-Vision pyobjc-framework-Quartz)")
        return
    lines = ["probe_dob_vision v1 (counts and masked lines only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    groups = defaultdict(list)
    for rid, r in sorted(reqs.items()):
        if r.pdf_path:
            groups[items.get(rid, {}).get("docType", "(not in reference)")].append(r)
    total, done, t0 = sum(len(v) for v in groups.values()), 0, time.time()
    for gname, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        s, samples = Counter(), []
        for r in rs:
            done += 1
            if done % 25 == 0:
                print(f"   {done}/{total}  {int(time.time() - t0)}s", file=sys.stderr)
            try:
                v = vision_ocr.text_of(r.pdf_path)
            except Exception as e:
                s["vision failed " + type(e).__name__] += 1
                continue
            t = (ocr.cached_text(r.pdf_path) or ("", {}))[0]
            both = v + "\n" + t
            req = match.parse_date(r.user_info.get("Requested DOB"))
            ppp = match.parse_date(r.user_info.get("DOB In PPP"))
            s["docs"] += 1
            s["words<30"] += len(re.findall(r"\w+", v)) < 30
            s["any date"] += bool(dobtext.dates_in(v))
            a, b = dobtext.find_dob(v, req), dobtext.find_dob(both, req)
            s["requested exact (vision)"] += a == "exact"
            s["requested exact (vision+tess)"] += b == "exact"
            s["requested one digit off (vision+tess)"] += b == "one digit off"
            if req and ppp and req != ppp:
                s["DOB changed"] += 1
                s["changed: requested exact"] += b == "exact"
                s["changed: requested one digit off"] += b == "one digit off"
                s["changed: PPP date shown"] += dobtext.find_dob(both, ppp) == "exact"
            s["age-as-on line"] += bool(dobtext.ages_as_on(both))
            docvars = electors.variants(r.user_info.get("Document Number", ""))
            if len(r.user_info.get("Document Number", "")) >= 6 and str(r.user_info.get("Uploaded Document", "")).startswith("Voter"):
                s["voter docs with number"] += 1
                s["EPIC in vision text"] += any(x in re.sub(r"[^A-Z0-9]", "", v.upper()) for x in docvars)
            if len(samples) < SAMPLES and len(re.findall(r"\w+", v)) >= 30:
                kept = [mask(l) for l in v.splitlines() if KEYWORD.search(l)]
                samples.append([k for k in kept if k][:LINES])
        lines.append(f"\n=== {gname}: {len(rs)} requests with a PDF ===")
        lines.append("   " + ", ".join(f"{k} {v}" for k, v in sorted(s.items())))
        for i, smp in enumerate(samples, 1):
            lines.append(f"   sample {i}:")
            lines.extend("      " + x for x in smp)
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
