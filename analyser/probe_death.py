"""What do the death-certificate verification sites return?  Masked layouts only (letters a, digits 9; labels kept).

  python -m analyser.probe_death
Takes up to 2 certificates per site type (CRS new link, CRS old link, NDMC, MCD) and prints, for each: status, which fields
the parser found, the masked lines, and for CRS the JSON calls the page made (path shapes and key names only).
Counts of every site type among the Marital requests come first.
"""
import re
from collections import Counter
from urllib.parse import urlparse

from . import load, qr
from .probe import mask_line
from .verify import crs, mcd, ndmc

PER_KIND = 2
ONLY = {"ndmc", "crs old"}   # CRS new and MCD were read correctly in v1


def kind_of(link):
    m = re.search(r"https?://[^\s|\"'<>]+", link or "")
    host = urlparse(m.group(0)).hostname if m else ""
    if host == "dc.crsorgi.gov.in":
        return "crs new", m.group(0)
    if host == "crsorgi.gov.in":
        return "crs old", m.group(0)
    if host == "bnd.ndmc.gov.in":
        return "ndmc", m.group(0)
    if host == "mcdonline.nic.in" or "Verified URL" in (link or ""):
        return "mcd", link
    return None, None


def main():
    print("probe_death v2 (masked output only)")
    counts, picked = Counter(), {}
    for r, _, _ in load.load_module("marital"):
        if not r or not r.pdf_path:
            continue
        kind, target = kind_of(qr.best_link(qr.decode_pdf(r.pdf_path)))
        if not kind:
            continue
        counts[kind] += 1
        if len(picked.setdefault(kind, [])) < PER_KIND:
            picked[kind].append(target)
    print("Marital certificates by site:", dict(counts))
    for kind, targets in picked.items():
        if kind not in ONLY:
            continue
        for i, target in enumerate(targets, 1):
            capture = [] if kind.startswith(("crs", "ndmc")) else None
            mod = {"crs new": crs, "crs old": crs, "ndmc": ndmc, "mcd": mcd}[kind]
            rec = mod.verify(target, capture) if capture is not None else mod.verify(target)
            print(f"\n=== {kind} #{i}: status={rec.status} error={rec.error or '-'} fields parsed={sorted(rec.fields)} "
                  f"text lines={len([l for l in rec.text.splitlines() if l.strip()])} ===")
            for line in [l for l in rec.text.splitlines() if l.strip()][:60]:
                print("   " + " | ".join(mask_line(part) for part in re.split(r"\t|\s{3,}", line.strip())))
            for method, path, keys in capture or []:
                print(f"   {'FINAL PAGE' if method == 'FINAL' else 'JSON call: ' + method} {path} {'keys=' + str(keys) if keys else ''}")


if __name__ == "__main__":
    main()
