"""Rajasthan Pehchan QR (http://pehchan.rajasthan.gov.in/rpt_qrcode.aspx?param=...)."""
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from .. import match
from .base import Record, fetch


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("br", "tr", "p", "div", "li", "table"):
            self.out.append("\n")
        if tag in ("td", "th"):
            self.out.append("\t")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_text(html):
    p = _Text()
    p.feed(html)
    text = "".join(p.out)
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines() if l.strip())


def candidate_urls(qr_url):
    u = urlparse(qr_url)
    if not u.query:
        return []
    paths = ["/pehchan2/rpt_qrcode.aspx", u.path]
    return [f"https://{u.hostname}{p}?{u.query}" for p in dict.fromkeys(paths)]


LABELS = [
    ("reg_no", r"Registration No\.?"), ("reg_date", r"Registration Date"), ("marriage_date", r"Date of Marriage"),
    ("groom_name", r"Groom Name"), ("groom_father", r"Groom.s Father Name"),
    ("bride_name", r"Bride Name"), ("bride_father", r"Bride.s Father Name"),
    ("signer", r"Signer.s Name/Designation"),
]
LABEL_RE = re.compile("(" + "|".join(p for _, p in LABELS) + r")\s*:")


def parse_certificate(text):
    """Fields of a Rajasthan Pehchan marriage record: no mothers and no dates of birth are shown."""
    flat = re.sub(r"\s+", " ", text)
    found = list(LABEL_RE.finditer(flat))
    out = {}
    for i, m in enumerate(found):
        key = next(k for k, pat in LABELS if re.fullmatch(pat, m.group(1)))
        end = found[i + 1].start() if i + 1 < len(found) else min(len(flat), m.end() + 80)
        value = flat[m.end():end].strip(" ,")
        if value and key not in out:
            out[key] = value
    for k in ("reg_date", "marriage_date"):
        d = match.parse_date(out.get(k, ""))
        if d:
            out[k] = d.isoformat()
        else:
            out.pop(k, None)
    out.pop("signer", None)
    return out


def verify(qr_url):
    rec = Record(source="pehchan")
    for url in candidate_urls(qr_url):
        data, err = fetch(url)
        if data:
            text = html_text(data.decode("utf-8", "replace"))
            fields = parse_certificate(text)
            if "marriage_date" in fields and "bride_name" in fields:
                rec.text, rec.fields, rec.status, rec.error = text, fields, "verified", ""
                return rec
            rec.error = "page had no certificate text"
        else:
            rec.error = err
    return rec
