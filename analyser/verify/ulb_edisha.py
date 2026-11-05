"""Haryana ULB (aid=14) and eDisha (aid=5) marriage certificates.

edisha.gov.in has been unreachable, so its query string is sent to
online.ulbharyana.gov.in, which returns the same official PDF.
"""
import io
import logging
import re
from datetime import date
from urllib.parse import urlparse

import pypdf

from .base import Record, fetch

logging.getLogger("pypdf").setLevel(logging.ERROR)  # official PDFs often have minor structure warnings

ULB_HOST = "online.ulbharyana.gov.in"
PATHS = ("/Default_VerifyCertificate.aspx", "/FM/Default_VerifyCertificate.aspx")


def candidate_urls(qr_url):
    p = urlparse(qr_url)
    if not p.query:
        return []
    # try the path the QR itself used first
    paths = PATHS[::-1] if p.hostname == ULB_HOST and p.path.startswith("/FM/") else PATHS
    return [f"https://{ULB_HOST}{path}?{p.query}" for path in paths]


def pdf_text(data, layout=False):
    reader = pypdf.PdfReader(io.BytesIO(data))
    kw = {"extraction_mode": "layout"} if layout else {}
    return "\n".join((pg.extract_text(**kw) or "") for pg in reader.pages)


LABELS = [
    ("marriage_date", r"Date of Marriage"), ("place", r"Place of Marriage"),
    ("bride_name", r"Bride Name"), ("dob", r"Date of Birth"), ("father", r"Father.s Name"),
    ("mother", r"Mother.s Name"), ("address", r"Permanent Address"),
    ("groom_name", r"Bridegroom Name"), ("reg_no", r"Registration No\.?"),
    ("reg_date", r"Registration Date"), ("issued_by", r"Issued by"),
]
LABEL_RE = re.compile("(" + "|".join(p for _, p in LABELS) + r")\s*:")
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(text):
    """'March 7 , 2026' (possibly split over lines) -> 'yyyy-mm-dd', or ''."""
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*,?\s*(\d{4})", text)
    if m and m.group(1)[:3].lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2))).isoformat()
        except ValueError:
            return ""
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return ""
    return ""


def parse_certificate(text):
    """Fields from the official marriage certificate text (ULB / eDisha layout).

    Labels are followed by their value; the bride block comes before the groom block.
    Returns a dict; dates are 'yyyy-mm-dd'. Fields not found are absent.
    """
    lines = [l for l in text.splitlines() if "://" not in l]  # drop the verification-link sentence
    flat = re.sub(r"\s+", " ", " ".join(lines))
    found = list(LABEL_RE.finditer(flat))
    out, role = {}, ""
    for i, m in enumerate(found):
        key = next(k for k, pat in LABELS if re.fullmatch(pat, m.group(1)))
        end = found[i + 1].start() if i + 1 < len(found) else len(flat)
        value = flat[m.end():end].strip(" ,")
        if key == "bride_name":
            role = "bride"
        elif key == "groom_name":
            role = "groom"
        if key in ("dob", "father", "mother", "address"):
            if not role:
                continue
            key = f"{role}_{key}"
        if key in out or not value:
            continue
        out[key] = value
    for k in [k for k in out if k.endswith("dob") or k in ("marriage_date", "reg_date")]:
        out[k] = parse_date(out[k])
        if not out[k]:
            del out[k]
    return out


def verify(qr_url):
    source = "edisha" if urlparse(qr_url).hostname == "edisha.gov.in" else "ulb"
    rec = Record(source=source)
    urls = candidate_urls(qr_url)
    if not urls:
        rec.error = "QR link has no query string"
        return rec
    for u in urls:
        data, err = fetch(u)
        if data and data[:5] == b"%PDF-":
            try:
                rec.text = pdf_text(data)
            except Exception as e:
                rec.error = "PDF unreadable " + type(e).__name__
                return rec
            if not rec.text.strip():
                rec.error = "official PDF has no text layer"
                return rec
            rec.fields = parse_certificate(rec.text)
            rec.status = "verified"
            return rec
        rec.error = err or "response was not a PDF"
    return rec
