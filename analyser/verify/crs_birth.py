"""CRS (crsorgi.gov.in) birth certificate verification page: rendered text of the record.

Same pages and browser handling as the death records (verify/crs.py): headless Chromium, a fresh context per certificate,
TLS on, a pause between certificates, only government hosts.  The rendered text is cached by URL hash; failures are not
cached.  Field parsing is added once the layout has been seen (probe_birth).
"""
import json
import re

from . import browser
from .base import CACHE, _key

MIN_GAP = 3.0
READY = r"registration\s*(number|no)[\s\S]*birth|birth[\s\S]*registration\s*(number|no)"


def text_of(url, capture=None):
    """(text, error) of the verification page, from the cache when present."""
    f = CACHE / f"{_key(url)}.crsbirth.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["text"], ""
    text, err = browser.render(url, READY, capture, gap_key="crs", min_gap=MIN_GAP)
    if err.startswith("TimeoutError") and "/web/index.php/" in url:
        text, err = browser.render(url, READY, capture, gap_key="crs", min_gap=MIN_GAP, timeout_ms=120_000, wait_until="commit")
    if text and not err and re.search(READY, text, re.I):
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
        f.chmod(0o600)
    return text, err


LABELS = {
    "registration number": "reg_no", "registration no": "reg_no", "name": "name", "gender": "gender", "sex": "gender",
    "dob": "dob", "date of birth": "dob", "name of mother": "mother", "mother name": "mother", "name of father": "father",
    "father name": "father", "place of birth": "place", "registration date": "reg_date", "date of registration": "reg_date",
    "registration unit name": "unit",
}


def parse(text):
    """Fields of the rendered record: reg_no, name, gender, dob, mother, father, place, reg_date, unit (dates ISO)."""
    from .. import dobtext, match
    from ..load import norm

    fields = {}
    for line in (text or "").splitlines():
        parts = [p.strip() for p in re.split(r"\t|\s{3,}", line.strip()) if p.strip()]
        if len(parts) < 2:
            continue
        key = LABELS.get(norm(parts[0]))
        if key and key not in fields:
            value = parts[1]
            if key in ("dob", "reg_date"):
                d = match.parse_date(value)
                if d is None:  # other styles: 12-Mar-2001, 12 March 2001, 12/03/01 ...
                    found = dobtext.dates_in(value)
                    d = next(iter(found)) if len(found) == 1 else None
                value = d.isoformat() if d else ""
            if value:
                fields[key] = value
    return fields


def verify(url, capture=None):
    from .base import Record

    rec = Record(source="crs birth")
    text, err = text_of(url, capture)
    rec.text = text
    rec.fields = parse(text) if text else {}
    if err:
        rec.error = err
    elif "dob" in rec.fields and "reg_no" in rec.fields:
        rec.status = "verified"
    else:
        rec.error = "page showed no birth record"
    return rec
