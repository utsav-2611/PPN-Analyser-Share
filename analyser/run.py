"""Run the rules over collected requests.  Dry run prints counts only (no names or numbers).

  python -m analyser.run --dry-run            Marriage requests (Marital rules come later), counts only
  python -m analyser.run                      analyse and save to store/results.json (see: python -m analyser.report)
  python -m analyser.run --workers 4          trial: analyse 4 requests at a time
Verifier responses are cached, so re-runs do not contact the official sites again.
"""
import argparse
import json
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from collections import Counter

from . import load, reasons, remark, rules_divorce, rules_dob, rules_marital, rules_marriage, store
from .rules_marriage import Decision


def decide(req):
    """Decision for one request, or None when its rules are not built yet."""
    if req.module == "marriage":
        if norm_type(req) == "divorced":
            return rules_divorce.analyse(req)
        return rules_marriage.analyse(req)
    if req.module == "marital":
        return rules_marital.analyse(req)
    if req.module == "dob":
        return rules_dob.analyse(req)
    return None


def norm_type(req):
    return load.norm(req.request_type)


def decide_for_store(req):
    """Like decide(), but a Marriage request without rules yet (Divorced) becomes a HOLD so it still gets a recommendation."""
    d = decide(req)
    if d is None and req.module == "marriage":
        body = "Divorce decree is not machine checked yet so officer to read the decree and decide"
        d = Decision("HOLD", remark.build("On hold", body, req), flags=["Decree not checked"], analysis=body, body=body)
    return d


def record_for(req, d, analysed_at):
    """The result record for one request and its Decision."""
    lists = [x for x in (req.tab, *(req.raw.get("tabs") or [])) if x in ("lly", "priority", "pending", "newRegistration")]
    return {
        "id": req.id, "module": req.module, "requestId": req.request_id, "name": req.name, "familyId": req.family_id,
        "lists": list(dict.fromkeys(lists)), "requestType": req.request_type, "flag": req.flag,
        "docType": req.user_info.get("Uploaded Document", "") if req.module == "dob" else
                   "Divorce decree" if load.norm(req.request_type) == "divorced" else "Marriage certificate",
        "facts": d.facts, "verification": {"status": d.verification_status, "text": d.verification_text},
        "analysis": d.analysis, "notes": "; ".join(d.flags), "recommendation": d.recommendation,
        "proposedRemark": d.remark,
        "rejectReason": reasons.pick(req.module, d.flags) if d.recommendation != "APPROVE" else "", "remarks": remark.alternatives(d, req), "collectedAt": req.raw.get("collected_at", ""), "analysedAt": analysed_at,
        "folder": str(req.folder), "hasPdf": bool(req.pdf_path), "hasPng": bool(req.window_png),
        "lly": req.is_lly,
    }


def _analyse_one(task):
    """Worker for a parallel run: (module, folder, analysed_at) -> ("ok", record) | ("skip", None) | ("error", exception name)."""
    module, folder, at = task
    try:
        folder = Path(folder)
        req = load.Request(module, folder, json.loads((folder / "case.json").read_text(encoding="utf-8")))
        d = decide_for_store(req)
        return ("ok", record_for(req, d, at)) if d is not None else ("skip", None)
    except Exception as e:
        return "error", type(e).__name__


def analyse_all(modules=("marriage", "marital", "dob"), progress=None, only_new=False, workers=1):
    """Analyse the collected requests (only those not in the store yet when only_new).  Returns (records, errors) where
    errors counts by exception type.  workers > 1 analyses that many requests at a time in separate processes (same results).

    `progress(module, done_in_module, module_total, done_overall, overall_total)` is called before each request and once at the end."""
    records, errors = [], Counter()
    at = store.now()
    have = set(store.read()["requests"]) if only_new else set()
    batches = {m: [t for t in load.load_module(m) if t[0] is None or t[0].id not in have] for m in modules}
    overall, finished = sum(len(b) for b in batches.values()), 0
    pool = ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) if workers > 1 else None
    for module, batch in batches.items():
        if pool:   # spawn, not fork: the Apple Vision / Objective-C libraries are not fork safe
            errors["unreadable case.json"] += sum(1 for t in batch if not t[0])
            tasks = [(module, str(t[0].folder), at) for t in batch if t[0]]
            for i, (kind, value) in enumerate(pool.map(_analyse_one, tasks)):
                if progress:
                    progress(module, i, len(batch), finished + i, overall)
                if kind == "ok":
                    records.append(value)
                elif kind == "error":
                    errors[value] += 1
            finished += len(batch)
            if progress:
                progress(module, len(batch), len(batch), finished, overall)
            continue
        for i, (req, _, err) in enumerate(batch):
            if progress:
                progress(module, i, len(batch), finished, overall)
            finished += 1
            if not req:
                errors["unreadable case.json"] += 1
                continue
            try:
                d = decide_for_store(req)
            except Exception as e:
                errors[type(e).__name__] += 1
                continue
            if d is not None:
                records.append(record_for(req, d, at))
        if progress:
            progress(module, len(batch), len(batch), finished, overall)
    if pool:
        pool.shutdown()
    return records, errors


def backfill_reasons(data):
    """Give requests analysed before reject reasons existed their suggested reason, from the flags already stored.
    Returns how many were filled."""
    n = 0
    for r in data["requests"].values():
        if r.get("recommendation") != "APPROVE" and not r.get("rejectReason") and r.get("module") in reasons.OPTIONS:
            r["rejectReason"] = reasons.pick(r["module"], r.get("notes") or "")
            n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print counts only; nothing is written")
    ap.add_argument("--all", action="store_true", help="analyse every collected request again (default: only those not analysed yet)")
    ap.add_argument("--workers", type=int, default=1, help="analyse this many requests at a time (trial; default 1 = one by one)")
    ap.add_argument("--modules", default=os.environ.get("PPN_ANALYSE_MODULES", ""), help="comma separated, e.g. marital,dob (default all)")
    args = ap.parse_args(argv)
    if not args.dry_run:
        print("run v3 (counts only; nothing is printed about people)")
        mods = tuple(m for m in args.modules.split(",") if m in load.MODULES) or ("marriage", "marital", "dob")
        records, errors = analyse_all(mods, None, only_new=not args.all, workers=max(args.workers, 1))
        with store.locked() as data:
            counts = store.merge_requests(data, records)
            filled = backfill_reasons(data)
        print("recommendations:", dict(Counter(r["recommendation"] for r in records)))
        store.lock_down()
        print("store:", counts, "| reject reasons filled:", filled)
        if errors:
            print("errors:", dict(errors))
        return
    print("run v2 (counts only)")
    totals, flags, errors, skipped = Counter(), Counter(), Counter(), Counter()
    for module in ("marriage", "marital"):
        for req, _, err in load.load_module(module):
            if not req:
                errors["unreadable case.json"] += 1
                continue
            try:
                d = decide(req)
            except Exception as e:
                errors[type(e).__name__] += 1
                continue
            if d is None:
                skipped[req.request_type or "(blank)"] += 1
                continue
            totals[d.recommendation] += 1
            for f in d.flags:
                flags[(d.recommendation, f)] += 1
    print("recommendations:", dict(totals))
    print("flags:")
    for (rec, f), n in sorted(flags.items()):
        print(f"  {rec} / {f}: {n}")
    print("not handled yet (rules not built):", dict(skipped))
    if errors:
        print("errors:", dict(errors))


if __name__ == "__main__":
    main()
