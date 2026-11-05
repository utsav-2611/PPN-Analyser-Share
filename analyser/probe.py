"""Show the layout of official-site records with the values masked, so the officer can
share it. Letters become a, digits 9; the text before a ':' (the label) is kept.

  python -m analyser.probe ulb [N]     fetch up to N ULB/eDisha certificates (default 3)
"""
import re
import sys
from collections import Counter
from urllib.parse import urlparse

from . import load, qr
from .verify import base, ulb_edisha


def mask_line(line):
    line = line.strip()
    if not line:
        return ""
    label, sep, value = line.partition(":")
    if sep and len(label) <= 40:
        return f"{label.strip()}: {qr.shape(value) if value.strip() else ''}"
    return qr.shape(line)


def pick(kind, n):
    hosts = {"ulb": ("edisha.gov.in", "online.ulbharyana.gov.in")}[kind]
    out = []
    for module in ("marriage", "marital"):
        for r, _, _ in load.load_module(module):
            if not r or not r.pdf_path:
                continue
            link = qr.best_link(qr.decode_pdf(r.pdf_path))
            m = re.search(r"https?://[^\s|\"'<>]+", link or "")
            if m and urlparse(m.group(0)).hostname in hosts:
                out.append((r, m.group(0)))
            if len(out) >= n:
                return out
    return out


def sequence(kind):
    """Print the first sample's lines in original order, masked, for normal and layout extraction."""
    (r, link), = pick(kind, 1)
    for u in ulb_edisha.candidate_urls(link):
        data, _ = base.fetch(u)
        if data and data[:5] == b"%PDF-":
            break
    for layout in (False, True):
        print(f"\n=== {'layout' if layout else 'normal'} extraction, in order ===")
        for line in ulb_edisha.pdf_text(data, layout).splitlines():
            if line.strip():
                lead = len(line) - len(line.lstrip())
                print(f"[{lead:>3}] " + " | ".join(mask_line(part) for part in re.split(r"\s{3,}", line.strip())))


def main():
    print("probe v2 (masked output only)")
    if "--seq" in sys.argv or "seq" in sys.argv:
        return sequence("ulb")
    kind = sys.argv[1] if len(sys.argv) > 1 else "ulb"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    for i, (r, link) in enumerate(pick(kind, n), 1):
        rec = ulb_edisha.verify(link)
        print(f"\n--- sample {i}: source={rec.source} status={rec.status} error={rec.error or '-'} ---")
        counts = Counter(mask_line(l) for l in rec.text.splitlines() if l.strip())
        for sig, c in counts.items():
            print(f"{c}x  {sig}")


if __name__ == "__main__":
    main()
