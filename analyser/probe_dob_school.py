"""What are the school documents the analyser cannot tell apart?  (cached text only, no network.)

  python -m analyser.probe_dob_school
Respects CRID_WORK_ROOT.  For documents read as 'school, type unclear' it counts the uploaded-document labels and which key
words occur, and prints the first lines of three of them with digits as 9 and words other than common document words as a.
Counts and masked shapes only.  Saves to store/probe_dob_school.txt.
"""
import re
from collections import Counter
from pathlib import Path

from . import load, ocr, rules_dob, vision_ocr
from .load import get
from .probe_dob_layout import mask

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "probe_dob_school.txt"
WORDS = ("school", "certificate", "class", "admission", "leaving", "transfer", "board", "examination", "marks", "roll",
         "register", "student", "pupil", "date of birth", "principal", "विद्यालय", "प्रमाण", "कक्षा", "छात्र", "जन्म", "स्कूल", "पाठशाला")


def main():
    lines = ["probe_dob_school v1 (counts and masked shapes only)", f"work root: {load.WORK_ROOT}"]
    labels, words, sizes, samples = Counter(), Counter(), Counter(), []
    n = 0
    for r, _, _ in load.load_module("dob"):
        if not r or not r.pdf_path:
            continue
        v = vision_ocr.cached_text(r.pdf_path)
        if v is None:
            continue
        both = v + "\n" + (ocr.cached_text(r.pdf_path) or ("", {}))[0]
        label = get(r.user_info, "Uploaded Document")
        if rules_dob.classify_text(both, label) != rules_dob.SCHOOL:
            continue
        n += 1
        labels[label] += 1
        count = len(re.findall(r"\w+", both))
        sizes["under 30 words" if count < 30 else "30 to 100 words" if count < 100 else "over 100 words"] += 1
        low = both.lower()
        words.update(w for w in WORDS if w in low)
        if len(samples) < 3 and count >= 30:
            samples.append([mask(x) for x in v.splitlines() if x.strip()][:22])
    lines.append(f"documents read as 'school, type unclear': {n}")
    lines.append("   uploaded-document labels: " + ", ".join(f"{k or '(blank)'} {c}" for k, c in labels.most_common()))
    lines.append("   size: " + ", ".join(f"{k} {c}" for k, c in sizes.most_common()))
    lines.append("   words present: " + ", ".join(f"{k} {c}" for k, c in words.most_common()))
    for k, sample in enumerate(samples, 1):
        lines.append(f"   --- first masked lines of document {k} ---")
        lines.extend("      " + x[:100] for x in sample)
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
