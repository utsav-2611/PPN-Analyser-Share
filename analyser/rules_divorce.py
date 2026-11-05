"""Decision rules for Divorced requests of the Marriage / Divorce PPN Update module (docs/RULES.md).

analyse(request, text_of=None) -> Decision.  `text_of(request) -> (text, info)` is injectable for tests; the default
reads document.pdf through ocr.py.  The decree is judged by its text (its QR is only an eCourts case number).

Order of checks: document present and readable -> it is a decree (REJECT for a criminal judgement, agreement, appeal,
notice or adjournment order; HOLD when the type is not recognised) -> parties -> custody against the request.
"""
from . import decree, match, remark
from .load import get, norm
from .rules_marriage import Decision, _done, _family_rows, _find_row

MIN_WORDS_FOR_REJECT = 300
CLEAR_TEXT_WORDS = 600   # enough clean text that an absent name is not an OCR accident
KIND_NAMES = {"criminal": "a criminal case judgement", "agreement": "a settlement or agreement",
              "appeal": "an appeal", "not_divorce": "a court paper that does not mention divorce or a decree", "notice": "a notice", "order_only": "an order that only lists or adjourns the case"}
CUSTODY_WORDS = {"applicant": "with the applicant", "spouse": "with the spouse", "both": "joint with visiting rights"}


def _text_of(req):
    from . import ocr
    return ocr.text_of(req.pdf_path)


def _gender(row):
    g = norm(get(row, "Gender"))[:1]
    return g if g in ("f", "m") else ""


def _yes(value):
    return norm(value) in ("yes", "y", "true")


def parties(req):
    """(applicant name, spouse name, spouse source, genders) from the request and the PPP family tables."""
    ui = req.user_info
    name = get(ui, "Name") or req.name
    spouse, source = get(ui, "Spouse Full Name"), "request"
    rows = (_family_rows(req, "old_family") or []) + (_family_rows(req, "new_family") or [])
    row = _find_row(rows, name)
    if not spouse and row and get(row, "Spouse Name"):
        spouse, source = get(row, "Spouse Name"), "PPP"
    if not spouse:
        source = "none"
    genders = {"applicant": _gender(row) if row else "", "spouse": ""}
    sp_row = _find_row(rows, spouse) if spouse else None
    if sp_row:
        genders["spouse"] = _gender(sp_row)
    if genders["applicant"] and not genders["spouse"]:
        genders["spouse"] = "m" if genders["applicant"] == "f" else "f"
    return name, spouse, source, genders


def analyse(req, text_of=None):
    ui = req.user_info
    name, spouse, source, genders = parties(req)
    court, asked = get(ui, "Name of Court", "Court Name"), match.parse_date(get(ui, "Date of Divorce", "Date of Court Order"))
    moved, whom = norm(get(ui, "Is Children Also Moved")), norm(get(ui, "Whom to Move"))
    facts = [["Request type", req.request_type], ["Applicant", name], ["Spouse", spouse or "(not on request or PPP)"],
             ["Date of divorce (request)", match.fmt_date(asked)], ["Court (request)", court],
             ["Whom to move", get(ui, "Whom to Move")], ["Children also moved", get(ui, "Is Children Also Moved")]]

    def done(rec, body, flags, analysis, status="na", vtext=""):
        return _done(req, rec, body, flags=flags, facts=facts, analysis=analysis, verification_status=status, verification_text=vtext)

    if not req.pdf_path:
        return done("HOLD", "No decree document was uploaded so officer to check the request", ["No document"], "No document.pdf")
    text, info = (text_of or _text_of)(req)
    kind, sig = decree.classify(text)
    vtext = f"Decree text read from {info.get('pages', '?')} page(s) by {info.get('method', '?')}; document type {kind}"

    if kind == "unreadable":
        return done("HOLD", "Decree text unreadable so officer to read the document", ["Decree unreadable"], vtext, "failed", vtext)
    if kind in KIND_NAMES:
        if sig["words"] < MIN_WORDS_FOR_REJECT:
            return done("HOLD", f"Document looks like {KIND_NAMES[kind]} but the text is too short to be sure so officer to read the document",
                        ["Decree type unsure"], vtext, "failed", vtext)
        return done("REJECT", f"Uploaded document is {KIND_NAMES[kind]} and not a decree of divorce so apply again with the attested copy of the decree of the court",
                    ["Not a decree"], vtext, "failed", vtext)
    if kind == "unknown":
        return done("HOLD", "Type of the uploaded document could not be recognised as a decree of divorce so officer to read the document",
                    ["Decree type unsure"], vtext, "failed", vtext)

    # ---- the document is a decree: parties --------------------------------------------------
    notes, flags, holds = [], [], []
    facts.append(["Decree text", vtext])
    if sig["script"] != "latin":
        holds.append("decree is not in English script so names were not machine checked")
        flags.append("Decree script")
    a_rank, a_role, _ = decree.find_party(name, text)
    s_rank, s_role, _ = decree.find_party(spouse, text) if spouse else ("missing", "", -1)
    ok = ("exact", "close", "partial")
    if sig["script"] == "latin":
        if a_rank not in ok:
            if spouse and s_rank not in ok and sig["words"] >= MIN_WORDS_FOR_REJECT:
                return done("REJECT", f"Decree does not name applicant {remark.clean(name)} or spouse {remark.clean(spouse)} so apply again with the decree of this couple",
                            ["Parties differ"], "Neither party found in decree text", "failed", vtext)
            if not spouse and sig["words"] >= CLEAR_TEXT_WORDS:
                return done("REJECT", f"Decree text read in full does not name applicant {remark.clean(name)} so apply again with the decree of this applicant",
                            ["Applicant not found"], "Applicant not found in a fully readable decree", "failed", vtext)
            holds.append(f"applicant {remark.clean(name)} not found in decree text")
            flags.append("Applicant not found")
        elif spouse and s_rank not in ok:
            # the applicant is the party whose status changes; the officer approves when only the spouse is not read by OCR
            notes.append(f"spouse {remark.clean(spouse)} not found in decree text by machine")
            flags.append("Spouse not found")
        elif not spouse:
            notes.append("spouse name is not on request or PPP so only applicant checked")
            flags.append("Spouse unknown")
    # ---- date and court ------------------------------------------------------------------
    if asked and asked not in decree.dates_in(text):
        notes.append(f"date of divorce {match.fmt_date(asked)} per request not seen in decree text")
        flags.append("Date not confirmed")
    if decree.court_found(court, text) is False:
        flags.append("Court not confirmed")
    petition = decree.petition_kind(text)
    facts.append(["Petition", {"mutual": "mutual consent (13B)", "contested": "contested"}.get(petition, "-")])

    # ---- custody against the request ------------------------------------------------------
    cu = decree.custody(text)
    facts.append(["Custody in decree", f"{cu['state']}{' / ' + cu['who'] if cu['who'] else ''}"])
    if cu["excerpt"]:
        facts.append(["Custody excerpt", cu["excerpt"]])
    side = decree.resolve_custody(cu, {"applicant": a_role, "spouse": s_role}, genders)
    mover = "spouse" if whom == "spouse" else "applicant" if whom else ""
    kids_move = _yes(get(ui, "Is Children Also Moved"))
    other = {"applicant": "spouse", "spouse": "applicant"}.get(mover, "")
    if cu["state"] == "stated" and side in ("applicant", "spouse", "both"):
        custody_text = f"custody of children {CUSTODY_WORDS[side]}"
        if side == "both":
            holds.append("custody of children is joint so officer to decide where the children are shown")
        elif mover and kids_move and side == other:
            return done("REJECT", f"Decree gives {custody_text} but request moves the children with the {mover} so children cannot move",
                        flags + ["Custody mismatch"], "Request moves children with the parent who does not have custody", "verified", vtext)
        elif mover and not kids_move and side == mover:
            holds.append(f"decree gives {custody_text} who is being moved but request does not move the children")
            flags.append("Custody mismatch")
    elif cu["state"] in ("stated", "unclear"):
        # the officer approves these when the children stay where they are; moving them needs the custody to be clear
        custody_text = "custody wording in decree could not be linked by machine to a parent"
        flags.append("Custody unclear")
        if kids_move:
            holds.append("request moves children but custody paragraph could not be linked to a parent")
    elif cu["state"] == "no children":
        custody_text = "decree records no children of the marriage"
        if kids_move:
            holds.append("request moves children but decree records no children")
            flags.append("Custody mismatch")
    else:
        custody_text = "custody of children not mentioned in decree"
        if kids_move:
            holds.append("request moves children but decree does not mention custody")
            flags.append("Custody missing")

    when = f"dated {match.fmt_date(asked)} " if asked else ""
    petition_text = {"mutual": "on mutual consent petition ", "contested": ""}.get(petition, "")
    base = (f"Decree of divorce {remark.clean(court) or 'of court'} {when}uploaded copy read by OCR dissolves marriage of "
            f"{remark.clean(name)}{' and ' + remark.clean(spouse) if spouse else ''} {petition_text}and {custody_text}")
    moves = ("status Divorced" if req.module == "marital"
             else f"children {'also moved' if kids_move else 'not moved'} as requested")
    analysis = "; ".join(holds + notes) or "Decree of divorce; parties, custody and request agree"
    if holds:
        return done("HOLD", f"{base} but " + " and ".join(holds) + " so officer to review", flags, analysis, "verified", vtext)
    tail = "".join(" " + n for n in notes)
    return done("APPROVE", f"{base} so {moves}{tail}", flags, analysis, "verified", vtext)
