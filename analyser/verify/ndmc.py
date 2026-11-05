"""NDMC (bnd.ndmc.gov.in/verify-certificate/<hex>) death certificate verification.

The page is a single-page app (a plain request returns an empty shell), so it is rendered in headless Chromium.
The site is rate limited: calls are 15 s apart and a 'Too many requests' page is never cached; the call is repeated after 65 s.
NDMC registration numbers on old certificates differ from the online numbers: that alone is not fraud.  The husband name is shown.
"""
import json
import re
import time

from . import browser, deathcommon
from .base import CACHE, Record, _key

GAP = 15
BACKOFF = 65
LIMITED = re.compile(r"too many requests|rate limit", re.I)
READY = r"date of (event|death)|name of (the )?deceased|too many requests|no record"


def render(url, capture=None):
    return browser.render(url, READY, capture, gap_key="ndmc", min_gap=GAP)


def verify(url, capture=None, retries=3):
    rec = Record(source="ndmc")
    f = CACHE / f"{_key(url)}.ndmc.json"
    if f.exists():
        text, err = json.loads(f.read_text(encoding="utf-8"))["text"], ""
    else:
        for attempt in range(retries):
            text, err = render(url, capture)
            if LIMITED.search(text) and len(text) < 2000:
                rec.error = "NDMC rate limit"
                time.sleep(BACKOFF)
                continue
            break
        else:
            return rec
    rec.text = text
    rec.fields = deathcommon.parse(text) if text else {}
    if err:
        rec.error = err
    elif "name" in rec.fields and ("dod" in rec.fields or "reg_no" in rec.fields):
        rec.status, rec.error = "verified", ""
        if not f.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    else:
        rec.error = "page showed no certificate record"
    return rec
