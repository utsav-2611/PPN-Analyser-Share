"""Remark building: letters, digits and spaces only, at most 500 characters, subordinate basis included."""
import re

from . import match

LIMIT = 500
REJECT_NOTE = "Applicant may come to the office of ADC with original document for physical verification of the document"
VALID = re.compile(r"^[A-Za-z0-9 ]{1,500}$")
_DATE = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})|(\d{4})-(\d{1,2})-(\d{1,2})")


def clean(text):
    """Keep letters, digits and spaces; everything else (including non Latin script) becomes a space."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", str(text or ""))).strip()


def valid(text):
    return bool(VALID.match(text or ""))


def first_date(text):
    """First date inside free text such as '11-03-2026 14:22', as 'dd mm yyyy', else ''."""
    m = _DATE.search(str(text or ""))
    if not m:
        return ""
    g = m.groups()
    try:
        d = match.parse_date(f"{g[0]}/{g[1]}/{g[2]}" if g[0] else f"{g[3]}-{g[4]}-{g[5]}")
    except Exception:
        d = None
    return match.fmt_date(d) if d else ""


def _verb(status):
    s = str(status or "").lower()
    for key, word in (("forward", "forwarded"), ("recommend", "recommended"), ("approv", "approved"),
                      ("reject", "rejected"), ("verif", "verified")):
        if key in s:
            return word
    return "reviewed"


def subordinate_parts(request):
    """[(role, name, verb, date)] from the ZCRIM / DCRIM / FCP remark blocks, in portal order."""
    out = []
    for role, name, block in request.subordinate_remarks():
        out.append((role, clean(name), _verb(block.get("Status")), first_date(block.get("Action Date"))))
    return out


def subordinate_text(parts, level):
    """level 0 full, 1 shorter, 2 role only, 3 nothing."""
    if not parts or level >= 3:
        return ""
    if level == 0:
        bits = [f"{r} {n} {v}" + (f" on {d}" if d else "") for r, n, v, d in parts]
        return " and ".join(bits) + " on basis of uploaded document"
    if level == 1:
        return " and ".join(f"{r} {v}" + (f" on {d}" if d else "") for r, n, v, d in parts) + " on uploaded document"
    return "after " + " and ".join(r for r, *_ in parts) + " verification"


def build(verdict, body, request=None, parts=None):
    """verdict: Approved | Rejected | On hold.  Returns a remark that passes VALID.

    The subordinate basis is shortened first; only then is the body cut at a word boundary.
    """
    parts = parts if parts is not None else (subordinate_parts(request) if request else [])
    tail = " " + REJECT_NOTE if verdict == "Rejected" else ""
    room = LIMIT - len(tail)
    head = clean(f"{verdict} {body}")
    for level in range(4):
        sub = subordinate_text(parts, level)
        text = clean(f"{head} {sub}")
        if len(text) <= room:
            return text + tail
    text = clean(head)[:room]
    if len(clean(head)) > room and " " in text:
        text = text[:text.rfind(" ")]
    return (text.strip() or verdict) + tail


_ASK = re.compile(r" (?:so (?:officer|DCRIM|ZCRIM|FCP|applicant|electoral|sent)|Applicant to|apply again|sent to|DCRIM to|officer to)\b")
VERDICTS = {"APPROVE": "Approved", "REJECT": "Rejected"}


def _subject(request):
    """A short neutral description of what was requested (no names), for remarks the analyser did not recommend."""
    from .load import get
    ui = request.user_info
    if request.module == "dob":
        doc = clean(get(ui, "Uploaded Document")) or "document"
        old, new = match.parse_date(get(ui, "DOB In PPP")), match.parse_date(get(ui, "Requested DOB"))
        if old and new:
            return f"{doc} uploaded for change of DOB from {match.fmt_date(old)} to {match.fmt_date(new)}"
        return f"{doc} uploaded for change of DOB"
    if request.module == "marital":
        cur, new = clean(get(ui, "Current Status In PPP")), clean(get(ui, "Requested Status In PPP"))
        return f"request for change of marital status from {cur} to {new}" if cur and new else "request for change of marital status"
    return f"{clean(request.request_type) or 'marriage'} request"


def alternatives(decision, request):
    """The remark to use whichever way the officer decides: {'APPROVE': ..., 'REJECT': ...}.

    The analyser's own verdict keeps its remark.  For the other verdict a neutral remark is built from the request:
    an approval says the officer examined the document and found it in order; a rejection after a HOLD carries the
    analyser's finding as the reason, and after an APPROVE says the document was not accepted on examination.
    The officer can edit either.
    """
    out = {}
    subject = _subject(request)
    findings = _ASK.split(decision.body or "", 1)[0].strip()[:250]
    for rec, verdict in VERDICTS.items():
        if decision.recommendation == rec:
            out[rec] = decision.remark
        elif rec == "APPROVE":
            out[rec] = build(verdict, f"{subject} examined by officer and found in order", request)
        elif decision.recommendation == "HOLD" and findings:
            out[rec] = build(verdict, f"{subject} {findings} Applicant to apply again with correct document", request)
        else:
            out[rec] = build(verdict, f"{subject} not accepted on examination by officer Applicant to apply again with correct document", request)
    return out
