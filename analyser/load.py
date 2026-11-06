"""Read collected PPN requests (case.json) with tolerant field getters.

Run as a dry-run report:  python -m analyser.load
The report prints counts only: no names, numbers or addresses.
"""
import json
import os
import re
from collections import Counter
from pathlib import Path

from . import settings

WORK_ROOT = settings.data_root()

# Electoral roll database used for the DOB voter-card check (follows the work root unless overridden).
ELECTORS_DB = settings.electors_db()

# Module keys and the folder each one is read from.
MODULES = {
    "dob": {"folder": "DOB", "title": "DOB Tagging"},
    "marital": {"folder": "Marital", "title": "Marital Tagging"},
    "marriage": {"folder": "Marriage-Divorce", "title": "Marriage/Divorce PPN Update"},
}


def norm(label):
    """Normalise a portal label for matching: lower case, single spaces, no punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", str(label or "").lower()).strip()


def get(mapping, *labels, default=""):
    """Case-insensitive, trimmed lookup of the first matching label in a dict."""
    if not isinstance(mapping, dict):
        return default
    wanted = [norm(l) for l in labels]
    index = {norm(k): v for k, v in mapping.items()}
    for w in wanted:
        if w in index and index[w] not in (None, ""):
            return str(index[w]).strip() if not isinstance(index[w], (dict, list)) else index[w]
    return default


class Request:
    """One collected request. Raw JSON stays in .raw; getters are tolerant."""

    def __init__(self, module, folder, raw):
        self.module = module
        self.folder = Path(folder)
        self.raw = raw
        self.request_id = str(raw.get("request_id") or self.folder.name)
        self.id = f"{module}__{self.request_id}"
        self.tab = raw.get("tab", "")
        self.list_row = raw.get("list_row") or {}
        self.case = raw.get("case") or {}
        self.user_info = self._section("User Info")

    def _section(self, legend):
        want = norm(legend)
        for k, v in self.case.items():
            if norm(k) == want and isinstance(v, dict):
                return v
        return {}

    # --- common fields -------------------------------------------------
    @property
    def family_id(self):
        return get(self.list_row, "FamilyID", "Family ID") or get(self.user_info, "Family ID", "Old Family ID")

    @property
    def name(self):
        return get(self.user_info, "Name", "Full Name") or get(self.list_row, "Name")

    @property
    def request_type(self):
        if self.module == "marriage":
            return get(self.list_row, "Request Type") or get(self.user_info, "Request Type")
        return get(self.user_info, "Requested Status In PPP") or get(self.list_row, "Requested MS PPP")

    @property
    def flag(self):
        return get(self.list_row, "Flag")

    @property
    def is_lly(self):
        return "lly" in norm(self.flag).split() or "lado lakshmi" in norm(self.flag) or "lly" in (self.raw.get("tabs") or [])

    @property
    def is_priority(self):
        return norm(self.tab) == "priority"

    # --- families -------------------------------------------------------
    def family(self, key="family"):
        rows = self.raw.get(key)
        return rows if isinstance(rows, list) else None

    # --- subordinate remarks -------------------------------------------
    def subordinate_remarks(self):
        """List of (role, officer name, block) for keys like 'ZCRIM Remark (NAME)'."""
        out = []
        for k, v in self.raw.items():
            m = re.match(r"\s*([A-Za-z]+)\s+Remark\s*\((.*)\)\s*$", k)
            if m and isinstance(v, dict):
                out.append((m.group(1).upper(), m.group(2).strip(), v))
        for src in (self.case,):
            for k, v in src.items():
                m = re.match(r"\s*([A-Za-z]+)\s+Remark\s*\((.*)\)\s*$", k)
                if m and isinstance(v, dict):
                    out.append((m.group(1).upper(), m.group(2).strip(), v))
        return out

    # --- files ----------------------------------------------------------
    @property
    def pdf_path(self):
        p = self.folder / "document.pdf"
        return p if p.exists() else None

    @property
    def window_png(self):
        p = self.folder / "case_window.png"
        return p if p.exists() else None


def load_module(module, root=None):
    """Yield (Request | None, request_folder, error) for every request folder of a module."""
    base = Path(root or WORK_ROOT) / MODULES[module]["folder"] / "requests"
    if not base.is_dir():
        return
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        f = folder / "case.json"
        try:
            yield Request(module, folder, json.loads(f.read_text(encoding="utf-8"))), folder, None
        except Exception as e:  # report type only, never content
            yield None, folder, type(e).__name__


def load_all(root=None):
    return [r for m in MODULES for r, _, _ in load_module(m, root) if r]


def report(root=None):
    print(f"Work root: {root or WORK_ROOT}")
    for module in MODULES:
        reqs, errors = [], Counter()
        for r, folder, err in load_module(module, root):
            if r:
                reqs.append(r)
            else:
                errors[err] += 1
        print(f"\n== {MODULES[module]['title']} ({module}) ==")
        print(f"requests parsed: {len(reqs)}   unreadable case.json: {sum(errors.values())} {dict(errors) or ''}")
        if not reqs:
            continue
        print("tabs:", dict(Counter(r.tab for r in reqs)))
        print("request types:", dict(Counter(r.request_type or "(blank)" for r in reqs)))
        print("flags:", dict(Counter(r.flag or "(none)" for r in reqs)))
        print(f"LLY: {sum(r.is_lly for r in reqs)}   priority: {sum(r.is_priority for r in reqs)}")
        print(f"document.pdf present: {sum(bool(r.pdf_path) for r in reqs)}/{len(reqs)}   "
              f"case_window.png present: {sum(bool(r.window_png) for r in reqs)}/{len(reqs)}")
        blank = Counter()
        for r in reqs:
            for label, val in (("family id", r.family_id), ("name", r.name), ("request type", r.request_type)):
                if not val:
                    blank[label] += 1
            if module == "marriage":
                for key in ("old_family", "new_family"):
                    if r.family(key) is None:
                        blank[key + " missing"] += 1
            elif r.family() is None:
                blank["family missing"] += 1
        print("fields blank/missing:", dict(blank) or "none")
        subs = Counter(role for r in reqs for role, _, _ in r.subordinate_remarks())
        print("subordinate remark blocks:", dict(subs) or "none")
        print("user-info labels seen (label: count):")
        labels = Counter(k for r in reqs for k in r.user_info)
        for k, n in sorted(labels.items()):
            print(f"   {k}: {n}")


if __name__ == "__main__":
    report()
