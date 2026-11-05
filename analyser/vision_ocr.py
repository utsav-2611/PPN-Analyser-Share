"""Text of a document PDF read with Apple Vision (offline, English).  Far better than tesseract on phone photos of
school certificates and voter cards.  Hindi is not supported by Vision on macOS 14, so Hindi labels need ocr.py.

  text_of(pdf_path) -> text          runs Vision on up to PAGES pages (cached by file hash, versioned)
  cached_text(pdf_path) -> text|None never runs Vision
  available() -> bool

The cache holds citizen document text, so it stays local like the other caches.  Nothing here prints text.
"""
import hashlib
import io
import json
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "store" / "cache" / "ocr_vision"
VERSION = 1
PAGES = 3
DPI = 300
MAX_SIDE = 3600  # pixels; larger scans are shrunk, which is faster and does not hurt recognition


def available():
    try:
        import Foundation  # noqa: F401
        import objc  # noqa: F401
        import Vision  # noqa: F401
        return True
    except Exception:
        return False


def _key(pdf_path):
    return hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:32]


def _file(pdf_path):
    return CACHE / f"{_key(pdf_path)}.v{VERSION}.json"


def cached_text(pdf_path):
    f = _file(pdf_path)
    return json.loads(f.read_text(encoding="utf-8"))["text"] if f.exists() else None


def _recognise(image):
    import Foundation
    import objc
    import Vision

    with objc.autorelease_pool():
        buf = io.BytesIO()
        image.save(buf, "PNG")
        raw = buf.getvalue()
        data = Foundation.NSData.dataWithBytes_length_(raw, len(raw))
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setRecognitionLanguages_(["en-US"])
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
        handler.performRequests_error_([req], None)
        lines = []
        for obs in req.results() or []:
            top = obs.topCandidates_(1)
            if top:
                lines.append(top[0].string())
        return "\n".join(lines)


def text_of(pdf_path):
    cached = cached_text(pdf_path)
    if cached is not None:
        return cached
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        parts = []
        for i in range(min(len(pdf), PAGES)):
            im = pdf[i].render(scale=DPI / 72).to_pil().convert("RGB")
            if max(im.size) > MAX_SIDE:
                k = MAX_SIDE / max(im.size)
                im = im.resize((int(im.width * k), int(im.height * k)))
            parts.append(_recognise(im))
    finally:
        pdf.close()
    text = "\n".join(parts)
    CACHE.mkdir(parents=True, exist_ok=True)
    CACHE.chmod(0o700)
    f = _file(pdf_path)
    f.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    f.chmod(0o600)
    return text


# ---- second chances for documents where the first pass misses the date --------------------------------------------
# (resolution, rotation) variants in order of how often they recovered a missed date on a sample of school certificates
VARIANTS = (("rot180", 300, 180), ("dpi200", 200, 0), ("rot90", 300, 90), ("rot270", 300, 270), ("dpi450", 450, 0))
VARIANT_CACHE = Path(__file__).resolve().parent.parent / "store" / "cache" / "ocr_variants"
VARIANT_MAX_SIDE = 5000


def variant_text(pdf_path, name, dpi, angle):
    """Vision text of the PDF read at another resolution or turned by `angle` degrees (cached by file hash)."""
    f = VARIANT_CACHE / f"{_key(pdf_path)}.{name}.v1.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["text"]
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        parts = []
        for i in range(min(len(pdf), PAGES)):
            im = pdf[i].render(scale=dpi / 72).to_pil().convert("RGB")
            if angle:
                im = im.rotate(angle, expand=True)
            if max(im.size) > VARIANT_MAX_SIDE:
                k = VARIANT_MAX_SIDE / max(im.size)
                im = im.resize((int(im.width * k), int(im.height * k)))
            parts.append(_recognise(im))
    finally:
        pdf.close()
    text = "\n".join(parts)
    VARIANT_CACHE.mkdir(parents=True, exist_ok=True)
    VARIANT_CACHE.chmod(0o700)
    f.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    f.chmod(0o600)
    return text
