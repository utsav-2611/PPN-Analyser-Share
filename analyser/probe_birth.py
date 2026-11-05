"""What does the CRS verification page return for a birth certificate?  Masked layouts only (letters a, digits 9; labels kept).

  python -m analyser.probe_birth
Respects CRID_WORK_ROOT.  Counts the CRS birth links among the DOB requests, then opens the first 2 on the official CRS
site (one at a time, 3 s apart, TLS on) and prints status, line count, the masked lines and the JSON calls the page made
(path shapes and key names only).  Saves to store/probe_birth.txt.
"""
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from . import load, qr
from .probe import mask_line
from .verify import crs_birth

OUT = Path(__file__).resolve().parent.parent / "store" / "probe_birth.txt"
PICK = 2


def main():
    lines = ["probe_birth v1 (masked output only)", f"work root: {load.WORK_ROOT}"]
    counts, picked = Counter(), []
    for r, _, _ in load.load_module("dob"):
        if not r or not r.pdf_path or not str(r.user_info.get("Uploaded Document", "")).lower().startswith("birth"):
            continue
        link = qr.best_link(qr.decode_pdf(r.pdf_path))
        m = re.search(r"https?://[^\s|\"'<>]+", link or "")
        host = urlparse(m.group(0)).hostname if m else None
        counts[host or "no link"] += 1
        if host in ("dc.crsorgi.gov.in", "crsorgi.gov.in") and len(picked) < PICK:
            picked.append(m.group(0))
    lines.append(f"birth certificates by QR host: {dict(counts)}")
    for i, url in enumerate(picked, 1):
        capture = []
        text, err = crs_birth.text_of(url, capture)
        body = [l for l in text.splitlines() if l.strip()]
        lines.append(f"\n=== birth record #{i}: error={err or '-'} lines={len(body)} ===")
        for line in body[:60]:
            lines.append("   " + " | ".join(mask_line(part) for part in re.split(r"\t|\s{3,}", line.strip())))
        for method, path, keys in capture:
            lines.append(f"   {'FINAL PAGE' if method == 'FINAL' else 'JSON call: ' + method} {path} {'keys=' + str(keys) if keys else ''}")
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
