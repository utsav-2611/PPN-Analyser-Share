"""Which fields parsed from the ULB / eDisha certificates? Counts only, no values.

  python -m analyser.probe_parse
"""
import re
from collections import Counter
from urllib.parse import urlparse

from . import load, qr
from .verify import ulb_edisha

EXPECTED = ["marriage_date", "place", "bride_name", "bride_dob", "bride_father", "bride_mother",
            "groom_name", "groom_dob", "groom_father", "groom_mother", "reg_no", "reg_date", "issued_by"]


def main():
    print("probe_parse v1 (counts only)")
    total, status, present = 0, Counter(), Counter()
    for module in ("marriage", "marital"):
        for r, _, _ in load.load_module(module):
            if not r or not r.pdf_path:
                continue
            link = qr.best_link(qr.decode_pdf(r.pdf_path))
            m = re.search(r"https?://[^\s|\"'<>]+", link or "")
            if not m or urlparse(m.group(0)).hostname not in ("edisha.gov.in", "online.ulbharyana.gov.in"):
                continue
            rec = ulb_edisha.verify(m.group(0))
            total += 1
            status[rec.status + (": " + rec.error if rec.error else "")] += 1
            for k in rec.fields:
                present[k] += 1
    print("certificates:", total, dict(status))
    for k in EXPECTED:
        print(f"  {k}: {present[k]}/{total}")


if __name__ == "__main__":
    main()
