"""Whole-document masked layouts for a few documents of the hard types (Vision text only).

  python -m analyser.probe_dob_samples
Respects CRID_WORK_ROOT.  Every line of 3 electoral roll certificates, 2 School Leaving Certificates and 2 middle school
certificates in which the requested DOB was not found, masked like probe_dob_layout (label words kept, all other words a,
digits 9).  Saves to store/probe_dob_samples.txt.
"""
import json
from pathlib import Path

from . import dobtext, load, match, vision_ocr
from .probe_dob_layout import mask

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_samples.txt"
REF = ROOT / "reference" / "palwal_dob_recommendations.json"
WANT = (("Electoral roll certificate", 3), ("School Leaving Certificate", 2), ("Middle School certificate", 2))
MAX_LINES = 60


def main():
    lines = ["probe_dob_samples v1 (masked output only)", f"work root: {load.WORK_ROOT}"]
    reqs = {r.request_id: r for r, _, _ in load.load_module("dob") if r}
    items = {str(it["requestId"]): it for it in json.loads(REF.read_text(encoding="utf-8"))["items"]}
    for group, n in WANT:
        taken = 0
        for rid, r in sorted(reqs.items()):
            if taken >= n:
                break
            if items.get(rid, {}).get("docType") != group or not r.pdf_path:
                continue
            text = vision_ocr.cached_text(r.pdf_path)
            if not text or dobtext.find_dob(text, match.parse_date(r.user_info.get("Requested DOB"))) == "exact":
                continue
            taken += 1
            lines.append(f"\n=== {group}, sample {taken} ===")
            shown = [mask(l) for l in text.splitlines()]
            lines.extend("   " + s for s in [x for x in shown if len(x) > 1][:MAX_LINES])
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
