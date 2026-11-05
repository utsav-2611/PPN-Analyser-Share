"""Maharashtra IGR e-Marriage QR: returns the certificate PDF (Special Marriage Act Form 16)."""
from .base import Record, fetch
from .ulb_edisha import pdf_text


def verify(qr_url):
    rec = Record(source="igr")
    data, err = fetch(qr_url)
    if not data or data[:5] != b"%PDF-":
        rec.error = err or "response was not a PDF"
        return rec
    try:
        rec.text = pdf_text(data)
    except Exception as e:
        rec.error = "PDF unreadable " + type(e).__name__
        return rec
    rec.status = "verified" if rec.text.strip() else "failed"
    rec.error = "" if rec.text.strip() else "official PDF has no text layer"
    return rec
