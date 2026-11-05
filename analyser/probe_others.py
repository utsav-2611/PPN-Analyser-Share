"""Masked, in-order layout of one Pehchan (Rajasthan) and one IGR Maharashtra certificate.

  python -m analyser.probe_others
Prints and saves to store/probe_others.txt.  Values are masked (letters a, digits 9); labels before ':' are kept.
"""
import re
from pathlib import Path
from urllib.parse import urlparse

from . import load, qr
from .probe import mask_line
from .verify import igr_maharashtra, pehchan

OUT = Path(__file__).resolve().parent.parent / "store" / "probe_others.txt"
KINDS = {"pehchan.rajasthan.gov.in": pehchan, "adjudication.igrmaharashtra.gov.in": igr_maharashtra}


def main():
    lines = ["probe_others v1 (masked output only)"]
    seen = set()
    for module in ("marriage", "marital"):
        for r, _, _ in load.load_module(module):
            if not r or not r.pdf_path:
                continue
            link = qr.best_link(qr.decode_pdf(r.pdf_path))
            m = re.search(r"https?://[^\s|\"'<>]+", link or "")
            host = urlparse(m.group(0)).hostname if m else None
            if host in KINDS and host not in seen:
                seen.add(host)
                rec = KINDS[host].verify(m.group(0))
                if host == "pehchan.rajasthan.gov.in":
                    from .verify import base
                    for url in pehchan.candidate_urls(m.group(0)):
                        data, err = base.fetch(url)
                        html = (data or b"").decode("utf-8", "replace")
                        tags = {t: len(re.findall(rf"<{t}\b", html, re.I)) for t in
                                ("table", "img", "iframe", "form", "script", "input", "a")}
                        lines.append(f"pehchan structure: path={urlparse(url).path} fetch_error={err or '-'} bytes={len(data or b'')} "
                                     f"starts_with_pdf={html[:5] == '%PDF-'} tags={tags} "
                                     f"words_in_title={len(re.findall(r'<title>(.*?)</title>', html, re.I | re.S))}")
                lines.append(f"\n=== {host}: status={rec.status} error={rec.error or '-'} ===")
                for line in rec.text.splitlines():
                    if line.strip():
                        lines.append("   " + " | ".join(mask_line(part) for part in re.split(r"\t|\s{3,}", line.strip())))
    text = "\n".join(lines)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text)
    print(text)
    print("\nsaved to", OUT)


if __name__ == "__main__":
    main()
