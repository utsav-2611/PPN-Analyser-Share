"""CRS (crsorgi.gov.in) death / birth certificate verification pages.

The new page (dc.crsorgi.gov.in/crs/verifyCertificate?id=...) is an Angular app and the old link
(crsorgi.gov.in/web/index.php/auth/deathCertificate/view/cert/D/<id>) redirects into it, so both are opened in headless
Chromium, one fresh browser context per certificate (otherwise the app can show the previous record).  TLS checking stays on.
The rendered text is cached by URL hash; failures are never cached.
"""
import json

from . import browser, deathcommon
from .base import CACHE, Record, _key

MIN_GAP = 3.0   # seconds between certificates: be polite to the site
HOSTS = ("crsorgi.gov.in", "dc.crsorgi.gov.in")


READY = r"registration\s*(number|no)[\s\S]*(death|deceased)|(death|deceased)[\s\S]*registration\s*(number|no)"


def render(url, capture=None):
    text, err = browser.render(url, READY, capture, gap_key="crs", min_gap=MIN_GAP)
    if err.startswith("TimeoutError") and "/web/index.php/" in url:
        # the old crsorgi.gov.in server redirects slowly: try once more with a long limit, not waiting for the page to settle
        text, err = browser.render(url, READY, capture, gap_key="crs", min_gap=MIN_GAP, timeout_ms=120_000, wait_until="commit")
    return text, err


def verify(url, capture=None):
    rec = Record(source="crs")
    f = CACHE / f"{_key(url)}.crs.json"
    if f.exists():
        text = json.loads(f.read_text(encoding="utf-8"))["text"]
        err = ""
    else:
        text, err = render(url, capture)
        if text and not err:
            fields_probe = deathcommon.parse(text)
            if "name" in fields_probe and "reg_no" in fields_probe:
                CACHE.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    rec.text = text
    rec.fields = deathcommon.parse(text) if text else {}
    if err:
        rec.error = err
    elif "name" in rec.fields and "reg_no" in rec.fields:
        rec.status = "verified"
    else:
        rec.error = "page showed no certificate record"
    return rec
