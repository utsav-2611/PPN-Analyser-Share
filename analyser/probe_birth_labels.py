"""Labels and masked values of the CRS birth record page, from the pages already cached by probe_birth (no network).

  python -m analyser.probe_birth_labels
A line or a label is printed as it is only when it is identical in the first two records (fixed page text); every value
is masked (letters a, digits 9).  Saves to store/probe_birth_labels.txt.
"""
import re
from pathlib import Path
from urllib.parse import urlparse

from . import load, qr
from .probe import mask_line
from .verify import crs_birth

OUT = Path(__file__).resolve().parent.parent / "store" / "probe_birth_labels.txt"


def main():
    lines = ["probe_birth_labels v1 (labels shown only when identical in both records; values masked)"]
    texts = []
    import os
    os.environ["PPN_CACHE_ONLY"] = "1"
    for r, _, _ in load.load_module("dob"):
        if len(texts) >= 2:
            break
        if not r or not r.pdf_path or not str(r.user_info.get("Uploaded Document", "")).lower().startswith("birth"):
            continue
        m = re.search(r"https?://[^\s|\"'<>]+", qr.best_link(qr.decode_pdf(r.pdf_path)) or "")
        if m and urlparse(m.group(0)).hostname in ("dc.crsorgi.gov.in", "crsorgi.gov.in"):
            text, err = crs_birth.text_of(m.group(0))
            if text:
                texts.append([l for l in text.splitlines() if l.strip()])
    if len(texts) < 2:
        lines.append("fewer than two cached birth records: run probe_birth first")
    else:
        a, b = texts
        lines.append(f"records: lines {len(a)} and {len(b)}")
        for i, (x, y) in enumerate(zip(a, b), 1):
            if x == y:
                lines.append(f"{i:3}  FIXED  {x.strip()[:100]}")
                continue
            px, py = re.split(r"\t|\s{3,}", x.strip()), re.split(r"\t|\s{3,}", y.strip())
            if len(px) == len(py) and len(px) > 1:
                shown = [p if p == q else "<" + mask_line(p) + ">" for p, q in zip(px, py)]
                lines.append(f"{i:3}  ROW    " + " | ".join(shown))
            else:
                lines.append(f"{i:3}  VALUE  " + mask_line(x))
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
