"""Which CRS birth pages could not be read?  (cache only: nothing is fetched.)

  python -m analyser.birth_diag
Respects CRID_WORK_ROOT.  For every birth certificate whose QR points to the CRS portal it counts, by link style (new
dc.crsorgi.gov.in or old crsorgi.gov.in), how many pages are in the cache (read before) and how many are not (failed or never
tried).  A page that failed is retried the next time the analyser runs.  Counts only.  Saves to store/birth_diag.txt.
"""
import os
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from . import load, qr
from .verify import crs_birth
from .verify.base import CACHE, _key

OUT = Path(__file__).resolve().parent.parent / "store" / "birth_diag.txt"


def main():
    os.environ["PPN_CACHE_ONLY"] = "1"
    lines = ["birth_diag v1 (counts only)", f"work root: {load.WORK_ROOT}"]
    c = Counter()
    for r, _, _ in load.load_module("dob"):
        if not r or not r.pdf_path or not str(r.user_info.get("Uploaded Document", "")).lower().startswith("birth"):
            continue
        m = re.search(r"https?://[^\s|\"'<>]+", qr.best_link(qr.decode_pdf(r.pdf_path)) or "")
        host = urlparse(m.group(0)).hostname if m else None
        if host not in ("dc.crsorgi.gov.in", "crsorgi.gov.in"):
            continue
        style = "new link (dc.crsorgi.gov.in)" if host == "dc.crsorgi.gov.in" else "old link (crsorgi.gov.in)"
        cached = (CACHE / f"{_key(m.group(0))}.crsbirth.json").exists()
        c[f"{style}: {'read ok' if cached else 'not read'}"] += 1
        if not cached:
            path_shape = re.sub(r"[A-Za-z0-9+/=_-]{12,}", "<id>", urlparse(m.group(0)).path)
            c[f"   not read, path shape {path_shape}"] += 1
    for k, v in sorted(c.items()):
        lines.append(f"   {k} {v}")
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
