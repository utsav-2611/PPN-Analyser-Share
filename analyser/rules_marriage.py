"""Decision rules for the Marriage / Divorce PPN Update module (Marriage requests).

analyse(request) -> Decision.  Dependencies are injectable so the rules can be tested on synthetic data:
  payloads(request) -> list of QR strings        (default: qr.decode_pdf, cached)
  verifier(url)     -> verify.base.Record        (default: ULB / eDisha verifier)
  issuer(request)   -> (state, read_by, note)    (default: issuer.issuer_of on the PDF)
Divorce requests are handled by rules_divorce (decree OCR), not here.
"""
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import match, qr, remark
from .load import get, norm

ULB_HOSTS = ("edisha.gov.in", "online.ulbharyana.gov.in")
PEHCHAN_HOSTS = ("pehchan.rajasthan.gov.in", "pehchan.raj.nic.in")
SOURCE_NAMES = {"edisha": "eDisha", "ulb": "ULB", "pehchan": "Pehchan Rajasthan"}
UNDER_AGE = {"bride": 18, "groom": 21}
QR_UNREADABLE = "QR is unreadable Applicant to visit the office of ADC with the original document"
RANK = {"exact": 3, "close": 2, "partial": 1}


@dataclass
class Decision:
    recommendation: str                 # APPROVE | REJECT | HOLD
    remark: str
    flags: list = field(default_factory=list)
    verification_status: str = "na"     # verified | failed | na
    verification_text: str = ""
    analysis: str = ""
    facts: list = field(default_factory=list)
    body: str = ""                      # the remark text without the verdict word and the subordinate basis


def _verdict(rec):
    return {"APPROVE": "Approved", "REJECT": "Rejected", "HOLD": "On hold"}[rec]


def _done(req, rec, body, **kw):
    return Decision(rec, remark.build(_verdict(rec), body, req), body=body, **kw)


def _family_rows(req, key):
    """Rows of a captured family table, or None.  A capture sometimes holds a single empty
    placeholder row ('no data'); a table without any named member counts as not captured."""
    rows = req.family(key)
    if not rows or not any(norm(_row_name(r)) for r in rows):
        return None
    return rows


def _row_name(row):
    return get(row, "Full Name", "Name")


def _find_row(rows, name):
    best, best_rank = None, 0
    for row in rows or []:
        rk = RANK.get(match.name_match(name, _row_name(row)), 0)
        if rk > best_rank:
            best, best_rank = row, rk
    return best


def _couple_children(req, bride, groom):
    """Birth dates of family-table members whose mother is the bride and whose father is the groom."""
    out = []
    for key in ("old_family", "new_family"):
        for row in _family_rows(req, key) or []:
            mother, father = get(row, "Mother Name"), get(row, "Father Name")
            if mother and match.acceptable(mother, bride) and (not father or match.acceptable(father, groom)):
                d = match.parse_date(get(row, "Date of Birth"))
                if d and d not in out:
                    out.append(d)
    return sorted(out)


def _placeholder(value):
    """'NA', 'No', '-' and other stand-ins that are not a name."""
    letters = re.sub(r"[^a-z]", "", norm(value))
    return len(letters) <= 2 or letters in ("none", "nil", "notavailable", "notapplicable", "unknown")


def _party(cert, name):
    """Which party of the certificate is `name`?  ('bride'|'groom'|'', rank)"""
    b = RANK.get(match.name_match(name, cert.get("bride_name")), 0)
    g = RANK.get(match.name_match(name, cert.get("groom_name")), 0)
    if max(b, g) == 0:
        return "", 0
    return ("bride" if b >= g else "groom"), max(b, g)


def _age_text(age):
    y, m = age
    return f"{y}" if m == 0 else f"{y} years {m} months"


def _outside_haryana(ui):
    place = norm(get(ui, "Place of Marriage"))
    inh = norm(get(ui, "Is Marriage in Haryana", "Is Marriage Registered In Haryana"))
    return "outside" in place or inh in ("no", "n", "false")


def analyse(req, payloads=None, verifier=None, issuer=None, igr_verifier=None, conclusion="marriage is established"):
    payloads = payloads or (lambda r: qr.decode_pdf(r.pdf_path) if r.pdf_path else [])
    ui = req.user_info
    name = get(ui, "Name") or req.name
    facts = [["Request type", req.request_type], ["Applicant", name],
             ["Spouse", get(ui, "Spouse Full Name")],
             ["Date of marriage (request)", get(ui, "Date Of Marriage")]]

    link = qr.best_link(payloads(req) or [])
    # ---- no QR / unreadable QR ------------------------------------------------------------
    if link is None:
        if issuer is None:
            from . import issuer as issuer_mod
            issuer = lambda r: issuer_mod.issuer_of(r.pdf_path) if r.pdf_path else ("unknown", "-", "")
        state = issuer(req)[0]
        if state == "haryana":
            return _done(req, "REJECT", QR_UNREADABLE, flags=["QR unreadable"], facts=facts,
                         analysis="No readable QR; certificate issued by Government of Haryana, which provides QR based documents")
        why = {"unknown": "issuer not readable", "mixed": "issuer unclear", "non government": "issued by a society or is an agreement"}.get(state, f"issued by {state}")
        return _done(req, "HOLD", f"No QR found and certificate {why} so officer to review", flags=["No QR"], facts=facts,
                     analysis=f"No readable QR; {why}")

    kind, host = qr.classify(link)
    if kind == "fake_host":
        return _done(req, "REJECT", f"QR points to non official site {remark.clean(host)} so certificate is not genuine",
                     flags=["Fake QR"], verification_status="failed", verification_text=f"QR host {host}", facts=facts,
                     analysis="QR points to a non government host")
    if kind == "plain_text":
        return _delhi_edistrict(req, link, ui, name, facts)
    if kind == "court_case":
        return _done(req, "HOLD", "QR is only a court case number and no marriage certificate QR so DCRIM to verify",
                     flags=["Case number QR"], facts=facts, analysis="QR holds a court case number")

    # ---- government QR whose site we can open ------------------------------------------------
    if host in ULB_HOSTS or host in PEHCHAN_HOSTS:
        verifier = verifier or (_default_verifier if host in ULB_HOSTS else _default_pehchan_verifier)
        rec = verifier(re.search(r"https?://[^\s|\"'<>]+", link).group(0))
        if rec.status != "verified":
            return _done(req, "HOLD", f"Official site did not return the certificate {remark.clean(rec.error)} so DCRIM to verify",
                         flags=["Site error"], verification_status="failed", verification_text=rec.error, facts=facts,
                         analysis="Official site could not be reached or returned no certificate")
        return _compare(req, rec, ui, name, facts, conclusion)

    if host == "adjudication.igrmaharashtra.gov.in":
        igr = igr_verifier or _default_igr_verifier
        rec = igr(re.search(r"https?://[^\s|\"'<>]+", link).group(0))
        if rec.status != "verified":
            return _done(req, "HOLD", f"Official IGR Maharashtra site did not return the certificate {remark.clean(rec.error)} so DCRIM to verify",
                         flags=["Site error"], verification_status="failed", verification_text=rec.error, facts=facts,
                         analysis="Official site could not be reached or returned no certificate")
        return _unopened(req, host, ui, name, facts, opened=True)

    if qr.host_allowed(host):  # we will have a verifier for it, but have not built it yet
        return _done(req, "HOLD", f"QR is on official site {remark.clean(host)} and verifier for this site is not built yet so DCRIM to verify",
                     flags=["Verifier missing"], facts=facts, analysis=f"No verifier yet for {host}")

    # ---- government site we cannot open: accepted as genuine (officer rule) --------------------
    return _unopened(req, host, ui, name, facts)


def _default_igr_verifier(url):
    from .verify import igr_maharashtra
    return igr_maharashtra.verify(url)


def _default_pehchan_verifier(url):
    from .verify import pehchan
    return pehchan.verify(url)


def _default_verifier(url):
    from .verify import ulb_edisha
    return ulb_edisha.verify(url)


# ---------------------------------------------------------------------------------------------
def _compare(req, rec, ui, name, facts, conclusion="marriage is established"):
    cert = rec.fields
    src = SOURCE_NAMES.get(rec.source, rec.source)
    mdate = match.parse_date(cert.get("marriage_date"))
    bride, groom = cert.get("bride_name", ""), cert.get("groom_name", "")
    reg = f"{src} Reg No {remark.clean(cert.get('reg_no'))} dated {match.fmt_date(match.parse_date(cert.get('reg_date')))}"
    if cert.get("issued_by"):
        reg += f" issued by {remark.clean(cert['issued_by'])}"
    base = f"Marriage certificate {reg} verified online on official {src} server shows marriage of {remark.clean(groom)} with {remark.clean(bride)} on {match.fmt_date(mdate)}"
    flags, rejects, holds, notes = [], [], [], []
    age_sentence = ""
    vt = f"{src} record: groom {groom}, bride {bride}, married {match.fmt_date(mdate)}"
    facts += [["Certificate groom", groom], ["Certificate bride", bride], ["Certificate marriage date", match.fmt_date(mdate)]]

    party, _ = _party(cert, name)
    other = "groom" if party == "bride" else "bride"
    spouse = get(ui, "Spouse Full Name")
    if not party:
        return _done(req, "REJECT", f"{base} but applicant {remark.clean(name)} is not named as bride or groom so apply again after correction of the certificate or PPP",
                     flags=["Name mismatch"], verification_status="verified", verification_text=vt, facts=facts,
                     analysis="Applicant is not named on the certificate")
    if spouse and not match.acceptable(spouse, cert.get(f"{other}_name")):
        rejects.append(f"spouse {remark.clean(spouse)} on request differs from {remark.clean(cert.get(other + '_name'))} on certificate so certificate does not belong to this PPP member")
        flags.append("Spouse mismatch")

    # parents of the applicant (request) and of the spouse (PPP family table) against the certificate
    def parent_check(who, fa, mo, cert_fa, cert_mo, flag):
        fa_ok = match.acceptable(fa, cert_fa) if fa and cert_fa else None
        mo_ok = match.acceptable(mo, cert_mo) if mo and cert_mo else None
        if fa_ok is False and mo_ok is False:
            rejects.append(f"{who} parents on certificate differ from PPP so certificate does not belong to this PPP member")
            flags.append(flag.replace("parent", "parents"))
        elif fa_ok is False:
            holds.append(f"{who} father on certificate {remark.clean(cert_fa)} differs from PPP while mother matches")
            flags.append(flag)
        elif mo_ok is False:  # mothers' names differ by nickname or an added word more often than fathers'
            notes.append(f"{who} mother on certificate {remark.clean(cert_mo)} differs from PPP while father matches")
            flags.append("Mother differs")

    parent_check(party, get(ui, "Father Name"), get(ui, "Mother Name"),
                 cert.get(f"{party}_father"), cert.get(f"{party}_mother"), "Parent mismatch")
    spouse_row = _find_row((_family_rows(req, "new_family") or []) + (_family_rows(req, "old_family") or []),
                           spouse or cert.get(f"{other}_name"))
    if spouse_row is None and not _placeholder(get(ui, "Spouse Father Name")):
        spouse_row = {"Father Name": get(ui, "Spouse Father Name")}  # Marital requests carry the spouse's father on the request
    if spouse_row:
        parent_check(other, get(spouse_row, "Father Name"), get(spouse_row, "Mother Name"),
                     cert.get(f"{other}_father"), cert.get(f"{other}_mother"), "Spouse parent mismatch")

    def dob_of(role):
        """Certificate DOB; else the request DOB for the applicant or the family-table DOB for the spouse."""
        d = match.parse_date(cert.get(f"{role}_dob"))
        if d:
            return d
        if role == party:
            return match.parse_date(get(ui, "Date of Birth"))
        return match.parse_date(get(spouse_row, "Date of Birth")) if spouse_row else None

    # dates and ages (official dates from the certificate)
    if mdate is None:
        holds.append("date of marriage on certificate could not be read")
    else:
        rdate = match.parse_date(get(ui, "Date Of Marriage"))
        if rdate and rdate != mdate:
            holds.append(f"date of marriage on request {match.fmt_date(rdate)} differs from certificate {match.fmt_date(mdate)}")
            flags.append("Date mismatch")
        ages = {}
        for role in ("bride", "groom"):
            dob = dob_of(role)
            if dob:
                ages[role] = match.age_on(dob, mdate)
        for role, limit in UNDER_AGE.items():
            if role in ages and ages[role][0] < limit:
                rejects.append(f"{role} was {_age_text(ages[role])} on date of marriage which is below {limit} so marriage is not valid")
                flags.append("Underage")
        # request DOB of the applicant against the certificate
        rdob = match.parse_date(get(ui, "Date of Birth"))
        cdob = match.parse_date(cert.get(f"{party}_dob"))
        if rdob and cdob and rdob != cdob:
            flags.append("DOB differs")
            rage = match.age_on(rdob, mdate)
            if rage[0] < UNDER_AGE[party] <= ages.get(party, (0,))[0]:
                holds.append(f"DOB on request {match.fmt_date(rdob)} would make {party} below {UNDER_AGE[party]} but certificate DOB {match.fmt_date(cdob)} does not")
            else:
                notes.append(f"DOB on request {match.fmt_date(rdob)} differs from certificate {match.fmt_date(cdob)}")
        age_sentence = " and ".join(f"{r} aged {_age_text(a)}" for r, a in ages.items()) if ages else ""

    # children of this couple born while the bride was a minor (or before she could be a mother)
    cdob = dob_of("bride")
    if cdob and mdate:
        for child_dob in _couple_children(req, bride, groom):
            conception = match.add_months(child_dob, -9)
            if match.age_on(cdob, conception)[0] < 18:
                holds.append(
                    f"spouse family shows a child of {remark.clean(bride)} and {remark.clean(groom)} born {match.fmt_date(child_dob)} "
                    + ("before the registered marriage " if child_dob < mdate else "")
                    + f"while bride born {match.fmt_date(cdob)} attained 18 only on {match.fmt_date(match.birthday(cdob, 18))} "
                    "so possibility of marriage while minor needs examination")
                flags.append("Child before 18")
                break

    # family tables
    old_rows, new_rows = _family_rows(req, "old_family"), _family_rows(req, "new_family")
    if old_rows is not None:
        row = _find_row(old_rows, name)
        if row is None:
            rejects.append("applicant is not a member of the family in the request")
            flags.append("Not in family")
        else:
            ppp_spouse = get(row, "Spouse Name")
            if ppp_spouse and spouse and not match.acceptable(ppp_spouse, cert.get(f"{other}_name")):
                holds.append(f"PPP already shows spouse {remark.clean(ppp_spouse)} for the applicant while certificate and request name "
                             f"{remark.clean(cert.get(other + '_name'))} so officer to confirm whether the PPP entry is a data error")
                flags.append("Married in PPP")
    if new_rows is None:
        notes.append("new family table not captured so confirm on portal")
        flags.append("Confirm on portal")
    if _outside_haryana(ui):
        flags.append("Outside Haryana")
        notes.append("marriage solemnized outside Haryana")

    analysis = "; ".join(rejects + holds + notes) or "Certificate verified; names, parents, dates and ages match"
    if rejects:
        return _done(req, "REJECT", f"{base} but " + " and ".join(rejects), flags=flags, verification_status="verified",
                     verification_text=vt, analysis=analysis, facts=facts)
    if holds:
        return _done(req, "HOLD", f"{base} but " + " and ".join(holds) + " so officer to review", flags=flags,
                     verification_status="verified", verification_text=vt, analysis=analysis, facts=facts)
    tail = (" " + age_sentence if age_sentence else "") + ("".join(" " + n for n in notes))
    return _done(req, "APPROVE", f"{base}{tail} so {conclusion}", flags=flags, verification_status="verified",
                 verification_text=vt, analysis=analysis, facts=facts)


def _delhi_edistrict(req, link, ui, name, facts):
    parts = [p.strip() for p in link.split("|")]
    if len(parts) >= 4 and re.fullmatch(r"\d+", parts[0]) and match.parse_date(parts[3].replace(" ", "")):
        qname, qdate = parts[1], match.parse_date(parts[3])
        spouse = get(ui, "Spouse Full Name")
        names_ok = match.acceptable(name, qname) or (spouse and match.acceptable(spouse, qname))
        rdate = match.parse_date(get(ui, "Date Of Marriage"))
        base = f"Delhi eDistrict marriage certificate number {remark.clean(parts[0])} QR text shows {remark.clean(qname)} married on {match.fmt_date(qdate)} and QR text not verified online"
        if not names_ok:
            return _done(req, "REJECT", f"{base} and name is neither applicant {remark.clean(name)} nor spouse so apply again with correct certificate",
                         flags=["Name mismatch", "QR text only"], verification_status="failed", facts=facts,
                         analysis="Name in QR text matches neither applicant nor spouse")
        if rdate and rdate != qdate:
            return _done(req, "HOLD", f"{base} but date on request {match.fmt_date(rdate)} differs so officer to review",
                         flags=["Date mismatch", "QR text only"], facts=facts, analysis="Date differs")
        return _done(req, "APPROVE", base, flags=["QR text only"], verification_status="na",
                     verification_text="Delhi eDistrict QR text only", facts=facts,
                     analysis="Decided on QR text because the Delhi site needs a captcha")
    return _done(req, "HOLD", "QR has no link and its format is not known so DCRIM to verify the certificate",
                 flags=["QR not verifiable"], facts=facts, analysis="QR is plain text of unknown format")


def _gender(req, name):
    """'f' / 'm' / '' from the Gender column of the applicant's family table row."""
    for key in ("old_family", "new_family"):
        row = _find_row(_family_rows(req, key), name)
        g = norm(get(row, "Gender")) if row else ""
        if g[:1] in ("f", "m"):
            return g[:1]
        if g in ("female", "male"):
            return g[0]
    return ""


def _unopened(req, host, ui, name, facts, opened=False):
    """QR on a government site we cannot open: genuine by host; check what the request itself shows."""
    mdate = match.parse_date(get(ui, "Date Of Marriage"))
    dob = match.parse_date(get(ui, "Date of Birth"))
    flags = ["Site not opened"]
    if opened:
        note = (f"QR verified on official government site {remark.clean(host)} and certificate is in Marathi so names were not machine checked "
                "and decided on PPP data")
        flags = ["Names not machine checked"]
    else:
        note = f"QR points to official government site {remark.clean(host)} and record was not opened so decided on PPP data"
    if mdate and dob:
        age = match.age_on(dob, mdate)
        gender = _gender(req, name)
        limit = {"f": 18, "m": 21}.get(gender)
        if limit and age[0] < limit:
            return _done(req, "REJECT", f"{note} applicant was {_age_text(age)} on date of marriage {match.fmt_date(mdate)} which is below {limit}",
                         flags=flags + ["Underage"], facts=facts, analysis=f"Applicant under {limit} on date of marriage")
        if not limit and age[0] < 18:
            return _done(req, "REJECT", f"{note} applicant was {_age_text(age)} on date of marriage {match.fmt_date(mdate)} which is below 18",
                         flags=flags + ["Underage"], facts=facts, analysis="Applicant under 18 on date of marriage")
        if not limit and age[0] < 21:
            return _done(req, "HOLD", f"{note} applicant aged {_age_text(age)} on date of marriage and gender is not in the family table so officer to review the 18 or 21 rule",
                         flags=flags, facts=facts, analysis="Age between 18 and 21, gender unknown")
    return _done(req, "APPROVE", note, flags=flags, verification_status="na",
                 verification_text=f"QR host {host} accepted as government site", facts=facts,
                 analysis="Government QR on a site the analyser does not open")
