"""How are Married requests of the Marital module filled in?  Shapes and categories only: no names or numbers.

  python -m analyser.probe_married
Makes no website calls (QR decoding is cached).  Letters become a, digits 9; a few plain words are shown as they are.
"""
import re
from urllib.parse import urlparse

from . import load, qr
from .load import get
from .probe_decree import SAFE, shape

PLAIN = SAFE | {"married", "unmarried", "widow", "widower", "divorced", "haryana", "india", "marriage certificate", "court marriage"}


def show(value):
    v = str(value or "").strip()
    return v if v.lower() in PLAIN else shape(v)


def main():
    print("probe_married v1 (shapes and categories only)")
    for req, _, _ in load.load_module("marital"):
        if not req or load.norm(req.request_type) != "married":
            continue
        link = qr.best_link(qr.decode_pdf(req.pdf_path)) if req.pdf_path else None
        kind, host = qr.classify(link) if link else ("no qr", "")
        print(f"\n--- {req.family_id}  QR: {kind} {host or ''}  pdf: {bool(req.pdf_path)}")
        print("   User Info:", {k: show(v) for k, v in req.user_info.items() if load.norm(k) not in ("mobile number",)})
        rows = req.family() or []
        me = next((r for r in rows if load.norm(get(r, "Full Name")) == load.norm(get(req.user_info, "Name"))), None)
        print(f"   family rows: {len(rows)}; applicant row: {'found' if me else 'not found'}"
              + (f" relation={get(me, 'Relation With HOF') or '-'} gender={get(me, 'Gender') or '-'} dob={'yes' if get(me, 'Date of Birth') else 'no'} "
                 f"spouse column {'filled' if get(me, 'Spouse Name') else 'blank'}" if me else ""))
        print("   subordinate remark blocks:", [role for role, _, _ in req.subordinate_remarks()])


if __name__ == "__main__":
    main()
