"""Which Marital certificates could not be read from the official site, and why?  Family ID, site kind and error code only.

  python -m analyser.site_errors
Cached successes are instant; each failing certificate is tried once again (CRS and NDMC are paced).
"""
import re
from urllib.parse import urlparse

from . import load, qr, rules_marital
from .verify import crs, mcd, ndmc


def main():
    print("site_errors v1 (Family ID, site kind, error code)")
    for req, _, _ in load.load_module("marital"):
        if not req or load.norm(req.request_type) not in ("widow", "widower") or not req.pdf_path:
            continue
        link = qr.best_link(qr.decode_pdf(req.pdf_path))
        kind, host = qr.classify(link) if link else ("none", "")
        m = re.search(r"https?://[^\s|\"'<>]+", link or "")
        if host in rules_marital.CRS_HOSTS:
            rec, label = crs.verify(m.group(0)), "crs new" if host == "dc.crsorgi.gov.in" else "crs old"
        elif host in rules_marital.NDMC_HOSTS:
            rec, label = ndmc.verify(m.group(0)), "ndmc"
        elif kind == "mcd_text" or host in rules_marital.MCD_HOSTS:
            rec, label = mcd.verify(link), "mcd"
        else:
            continue
        if rec.status != "verified":
            lines = len([l for l in rec.text.splitlines() if l.strip()])
            print(f"  {req.family_id} | {label} | {rec.error} | text lines {lines} | fields {sorted(rec.fields)}")


if __name__ == "__main__":
    main()
