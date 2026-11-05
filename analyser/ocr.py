"""Text of a court decree PDF: text layer where present, OCR (tesseract eng+hin) for scanned pages.

  text_of(pdf_path) -> (text, info)   info = {"pages": n, "layer_pages": k, "ocr_pages": m, "method": "layer|ocr|mixed|none"}

Results are cached in store/cache/ocr/ by file hash (versioned).  The cache holds decree text, so it stays local like
the other caches.  Nothing here prints text.
"""
import hashlib
import json
import re
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "store" / "cache" / "ocr"
VERSION = 1
MAX_PAGES = 15        # custody is usually in the last pages, so the whole decree is read up to this limit
MIN_LAYER_CHARS = 80  # letters/digits needed on a page before its text layer is trusted
DPI = 200


def _words(text):
    return len(re.sub(r"\W", "", text or ""))


def _read(pdf_path):
    import pypdf
    import pypdfium2 as pdfium

    layers = []
    try:
        layers = [(pg.extract_text() or "") for pg in list(pypdf.PdfReader(str(pdf_path)).pages)[:MAX_PAGES]]
    except Exception:
        pass
    pdf = pdfium.PdfDocument(str(pdf_path))
    parts, layer_pages, ocr_pages = [], 0, 0
    try:
        n = min(len(pdf), MAX_PAGES)
        for i in range(n):
            layer = layers[i] if i < len(layers) else ""
            if _words(layer) >= MIN_LAYER_CHARS:
                parts.append(layer)
                layer_pages += 1
                continue
            from .issuer import ocr_page
            parts.append(ocr_page(pdf[i].render(scale=DPI / 72).to_pil().convert("L")))
            ocr_pages += 1
        total = len(pdf)
    finally:
        pdf.close()
    method = "none" if not (layer_pages or ocr_pages) else "layer" if not ocr_pages else "ocr" if not layer_pages else "mixed"
    return "\n".join(parts), {"pages": total, "layer_pages": layer_pages, "ocr_pages": ocr_pages, "method": method}


def text_of(pdf_path):
    pdf_path = Path(pdf_path)
    key = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:32]
    cached = CACHE / f"{key}.v{VERSION}.json"
    if cached.exists():
        d = json.loads(cached.read_text(encoding="utf-8"))
        return d["text"], d["info"]
    text, info = _read(pdf_path)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"text": text, "info": info}, ensure_ascii=False), encoding="utf-8")
    return text, info


def cached_text(pdf_path):
    """Like text_of, but never runs OCR: (text, info) from the cache, or None when this PDF is not cached yet."""
    pdf_path = Path(pdf_path)
    key = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:32]
    cached = CACHE / f"{key}.v{VERSION}.json"
    if not cached.exists():
        return None
    d = json.loads(cached.read_text(encoding="utf-8"))
    return d["text"], d["info"]
