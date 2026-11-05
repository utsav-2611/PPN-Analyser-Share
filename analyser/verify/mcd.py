"""MCD Delhi death certificates.  The QR holds text:

  Name Of The Deceased ... Registration No ... Verified URL: https://mcdonline.nic.in/rbd/web/citizen/hospital/verifyCertificate?...

The URL is fetched and its 'Certificate Details' block parsed.  The site is down for maintenance 23:00-24:00 IST (it then says
'No Record Found'), which is reported as such and not as a mismatch.
"""
import re
from datetime import datetime, timedelta, timezone

from . import deathcommon
from .base import CACHE, Record, _key, fetch

IST = timezone(timedelta(hours=5, minutes=30))
URL_RE = re.compile(r"Verified URL\s*:?\s*(https?://[^\s|\"'<>]+)", re.I)


def verify_url(qr_text):
    m = URL_RE.search(qr_text) or re.search(r"(https?://[^\s|\"'<>]+)", qr_text)
    return m.group(1) if m else None


def verify(qr_text, now=None):
    rec = Record(source="mcd")
    url = verify_url(qr_text)
    if not url:
        rec.error = "QR text has no verification URL"
        return rec
    data, err = fetch(url)
    if not data:
        rec.error = err or "no response"
        return rec
    text = deathcommon.html_lines(data.decode("utf-8", "replace"))
    block = re.split(r"certificate details", text, maxsplit=1, flags=re.I)
    text = block[1] if len(block) == 2 else text
    rec.text, rec.fields = text, deathcommon.parse(text)
    if "name" in rec.fields and ("dod" in rec.fields or "reg_no" in rec.fields):
        rec.status = "verified"
    else:
        hour = (now or datetime.now(IST)).hour
        rec.error = "No Record Found (site maintenance 23:00 to 24:00)" if hour == 23 else "page showed no certificate record"
        if "no record found" in text.lower() and hour != 23:
            rec.error = "No Record Found"
        (CACHE / f"{_key(url)}.bin").unlink(missing_ok=True)  # never keep a failed page: maintenance ends
    return rec
