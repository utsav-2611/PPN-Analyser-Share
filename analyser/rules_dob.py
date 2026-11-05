"""Rules for DOB Tagging requests (docs/RULES.md, DOB; reference comparison on the Palwal set).

  analyse(req, evidence=None) -> Decision
Evidence (what the document shows) is gathered by `gather()` from the PDF; tests pass an Evidence directly.

Accepted documents: Voter ID issued 2019 or before, Matriculation / Secondary / Middle school board certificate,
School Leaving Certificate (with a copy of the school entry exit register), Passport, Government ID card (armed forces
discharge certificate), Birth certificate verified through its QR, Electoral roll certificate (checked against the roll).

Officer's changes of 23 10 2026:
 1. full DOB readable -> the whole date must match; DOB date unreadable but year readable -> the year must match
 2. SLC needs the register copy (present, readable or not); from a Haryana school it is accepted for any change, from a
    school outside Haryana a change of more than 2 years is rejected; HOLD only when unreadable
 3. voter ID whose EPIC is not in the electoral roll -> REJECT
 5. electoral roll certificate: EPIC checked against the roll; certificate agrees with the roll -> APPROVE, differs ->
    REJECT, EPIC not in the roll -> HOLD for the Election office to verify the certificate
 7. no document -> REJECT
"""
import re
from dataclasses import dataclass, field
from datetime import date

from . import dobtext, electors, match, qr, remark
from .load import get, norm
from .rules_marriage import Decision

BOARD, SLC, VOTER, BIRTH, PASSPORT, GOVT_ID, ROLL_CERT = "board", "slc", "voter", "birth", "passport", "govt_id", "roll_certificate"
SCHOOL = "school"          # a school document that could not be told apart (board certificate or SLC)
NAMES = {BOARD: "Board certificate", SLC: "School Leaving Certificate", VOTER: "Voter ID", BIRTH: "Birth certificate",
         PASSPORT: "Passport", GOVT_ID: "Government ID card", ROLL_CERT: "Electoral roll certificate",
         SCHOOL: "School certificate", "unknown": "Document"}
MAX_SLC_CHANGE_MONTHS = 24
LAST_VOTER_ISSUE_YEAR = 2019
OTHER_STATES = ("andhra pradesh", "bihar", "chandigarh", "chhattisgarh", "delhi", "gujarat", "himachal", "jammu", "jharkhand",
                "karnataka", "kerala", "madhya pradesh", "maharashtra", "odisha", "orissa", "punjab", "rajasthan",
                "tamil nadu", "telangana", "uttar pradesh", "uttarakhand", "west bengal")


@dataclass
class Evidence:
    doc_class: str = "unknown"     # board | slc | school | voter | birth | passport | govt_id | roll_certificate | none | unknown
    readable: bool = True          # enough text was read from the document
    dob_found: str = None          # 'exact' | 'one digit off' | None   (requested DOB in the document text)
    ppp_shown: bool = False        # the old (PPP) DOB is written in the document instead
    ages: list = field(default_factory=list)       # [(as on date, age)] from a voter card
    epic_rows: list = None         # electoral roll rows for the card's EPIC; None when not applicable
    epic_text: str = ""            # EPIC as typed on the request
    issue_year: int = None         # voter card issue year, when read
    qr_kind: str = "none"          # none | official | fake_host | plain_text | court_case | mcd_text
    qr_host: str = ""
    qr_opened: bool = False
    issuer: str = ""               # for a certificate without QR: haryana | other state | unknown ...
    birth_record: dict = None      # {'dob': date, 'name', 'father', 'mother', 'reg_no'} from the official birth record
    diary: str = ""                # electoral roll certificate diary number / date, when read
    discharge_dob: object = None   # armed forces discharge certificate DOB typed on the request
    dob_dates: set = field(default_factory=set)    # full dates on the document's date-of-birth lines
    dob_years: set = field(default_factory=set)    # years on those lines (also when the day or month is unreadable)
    register_copy: bool = None     # SLC: a copy of the school entry exit register is present (readable or not)
    school_state: str = "unknown"  # SLC: haryana | other | unknown
    plain_age: int = None          # 'Date of Birth / Age : 35' written without a date (voter card, roll certificate)


def _verdict(rec):
    return {"APPROVE": "Approved", "REJECT": "Rejected", "HOLD": "On hold"}[rec]


def _done(req, rec, body, **kw):
    return Decision(rec, remark.build(_verdict(rec), body, req), body=body, **kw)


def _over_two_years(ppp, req):
    return not (match.add_months(ppp, -MAX_SLC_CHANGE_MONTHS) <= req <= match.add_months(ppp, MAX_SLC_CHANGE_MONTHS))


def classify_text(text, label=""):
    """Document class from the OCR text and the request's 'Uploaded Document' label."""
    t = (text or "").lower()
    lab = norm(label)
    if "discharge" in lab:
        return GOVT_ID
    if lab.startswith("passport"):
        return PASSPORT
    if lab.startswith("birth"):
        return BIRTH
    if re.search(r"electoral roll|मतदाता सूची|diary", t) and re.search(r"certificate|प्रमाण", t) and \
            not re.search(r"elector'?s? name|epic no|photo identity", t):
        return ROLL_CERT
    if lab.startswith("voter") or re.search(r"elector'?s? name|photo identity card|election commission of india", t):
        return VOTER
    if re.search(r"school leaving|transfer certificate|withdrawal|admission no|विद्यालय छोड़ने|स्कूल छोड़ने|छोड़ने का प्रमाण|स्थानान्तरण|स्थानांतरण", t):
        return SLC
    if re.search(r"board of school education|secondary education|matriculation|senior secondary|middle school|"
                 r"roll no|marks|माध्यमिक|बोर्ड|"
                 r"secondary\s+(?:school\s+)?(?:examination|certificate)|high\s*school|दसवीं|हाई\s?स्कूल", t):
        return BOARD
    if "school" in lab or "matric" in lab:
        return SCHOOL
    return "unknown"


def _facts(req, ev):
    ui = req.user_info
    return [["Uploaded document", get(ui, "Uploaded Document")], ["Document read as", NAMES.get(ev.doc_class, ev.doc_class)],
            ["DOB in PPP", get(ui, "DOB In PPP")], ["Requested DOB", get(ui, "Requested DOB")],
            ["Document number", get(ui, "Document Number")]]


def analyse(req, evidence=None):
    ui = req.user_info
    ppp, new = match.parse_date(get(ui, "DOB In PPP")), match.parse_date(get(ui, "Requested DOB"))
    ev = evidence if evidence is not None else gather(req)
    facts = _facts(req, ev)
    name = NAMES.get(ev.doc_class, "Document")
    if new is None or ppp is None:
        return _done(req, "HOLD", "DOB on the request or in PPP could not be read so officer to review", flags=["DOB unreadable"], facts=facts)
    changed = ppp != new
    change = f"requested DOB {match.fmt_date(new)} differs from PPP DOB {match.fmt_date(ppp)}" if changed else \
        f"requested DOB {match.fmt_date(new)} same as PPP DOB so no change"
    base = dict(facts=facts)

    if ev.doc_class == "none":
        return _done(req, "REJECT", "No document uploaded so applicant to upload a valid DOB document", flags=["No document"], **base)
    if ev.doc_class == ROLL_CERT:
        return _roll_certificate(req, ev, new, base)

    if ev.doc_class == SLC:
        early = _slc(req, ev, ppp, new, changed, change, base)
        if early:
            return early
    if ev.doc_class == SCHOOL and changed and _over_two_years(ppp, new):
        return _done(req, "HOLD", f"{change} by more than 2 years and school document type unclear so officer to check whether it is a School Leaving Certificate",
                     flags=["School document type unclear"], **base)

    if ev.doc_class == BIRTH:
        return _birth(req, ev, new, ppp, changed, change, base)
    if ev.doc_class == VOTER:
        return _voter(req, ev, new, ppp, changed, change, base)

    if ev.discharge_dob and ev.doc_class == GOVT_ID:
        if ev.discharge_dob == new:
            return _done(req, "APPROVE", f"Armed forces discharge certificate shows DOB {match.fmt_date(new)} same as requested DOB and {change}",
                         flags=["Discharge certificate"], **base)
        return _done(req, "HOLD", f"Discharge certificate DOB {match.fmt_date(ev.discharge_dob)} differs from requested DOB {match.fmt_date(new)} so officer to review",
                     flags=["Discharge DOB differs"], **base)
    return _dob_check(req, ev, new, ppp, changed, change, name, base)


def _dob_check(req, ev, new, ppp, changed, change, name, base):
    """Compare the requested DOB with what the document says (officer's rule 1, 23 10 2026): a readable full date must
    match completely; when the date is not readable but the year is, the year must match."""
    shown = match.fmt_date
    if ev.dob_found == "exact":
        return _done(req, "APPROVE", f"{name} shows DOB {shown(new)} same as requested DOB and {change}",
                     flags=["DOB read from document"], analysis=f"{name} shows the requested DOB", **base)
    if not ev.readable and not (ev.dob_dates or ev.dob_years):
        return _done(req, "HOLD", f"{name} text could not be read by the analyser so officer to read the document and check DOB {shown(new)}",
                     flags=["Document not read"], **base)
    if ev.dob_found == "one digit off" or any(sum(a != b for a, b in zip(f"{d:%d%m%Y}", f"{new:%d%m%Y}")) == 1 for d in ev.dob_dates):
        return _done(req, "HOLD", f"{name} shows a date that differs from requested DOB {shown(new)} by one digit so officer to read the document",
                     flags=["DOB one digit off"], **base)
    if len(ev.dob_dates) == 1:
        (doc,) = ev.dob_dates
        return _done(req, "REJECT", f"{name} shows DOB {shown(doc)} which does not match requested DOB {shown(new)}",
                     flags=["DOB differs from document"], analysis="Full date on the document differs from the requested DOB", **base)
    if len(ev.dob_dates) > 1:
        return _done(req, "HOLD", f"{name} shows several dates near date of birth and none is requested DOB {shown(new)} so officer to read the document",
                     flags=["Several dates"], **base)
    if ev.dob_years:
        if new.year in ev.dob_years:
            return _done(req, "APPROVE", f"{name} date of birth is not fully readable but year {new.year} is readable and same as requested DOB {shown(new)} and {change}",
                         flags=["Year only matches"], analysis="Only the year of birth could be read and it matches", **base)
        years = " ".join(str(y) for y in sorted(ev.dob_years))
        return _done(req, "REJECT", f"{name} date of birth is not fully readable but shows year {years} and requested DOB {shown(new)} is of year {new.year}",
                     flags=["Year differs from document"], **base)
    shown_old = " and the old PPP DOB is written there instead" if ev.ppp_shown and changed else ""
    return _done(req, "HOLD", f"Requested DOB {shown(new)} not found in {name} text{shown_old} so officer to read the document",
                 flags=["DOB not found in document"], **base)


def _slc(req, ev, ppp, new, changed, change, base):
    """School Leaving Certificate checks; returns a Decision to stop with, or None to go on to the DOB check."""
    if ev.register_copy is False:
        return _done(req, "REJECT", "School Leaving Certificate is not accompanied by a copy of the school entry exit register so applicant to upload the register copy with the certificate",
                     flags=["Register copy missing"], **base)
    if changed and _over_two_years(ppp, new):
        if ev.school_state == "other":
            return _done(req, "REJECT", f"School Leaving Certificate of a school outside Haryana is not accepted for a change of more than 2 years and {change}",
                         flags=["SLC outside Haryana, change over 2 years"], **base)
        if ev.school_state != "haryana":
            return _done(req, "HOLD", f"{change} by more than 2 years and state of the school on the School Leaving Certificate could not be read so officer to check",
                         flags=["School state unreadable"], **base)
    return None


def _voter(req, ev, new, ppp, changed, change, base):
    epic = remark.clean(ev.epic_text or get(req.user_info, "Document Number"))
    if ev.issue_year and ev.issue_year > LAST_VOTER_ISSUE_YEAR:
        return _done(req, "REJECT", f"Voter ID issued in {ev.issue_year} is after {LAST_VOTER_ISSUE_YEAR} and is not accepted for DOB",
                     flags=["Voter ID issued after 2019"], **base)
    if ev.epic_rows is not None and not ev.epic_rows:
        return _done(req, "REJECT", f"EPIC {epic} of the voter ID is not found in the electoral roll so voter ID is not verified",
                     flags=["EPIC not in roll"], **base)
    in_roll = "EPIC verified in electoral roll"
    if ev.ages:
        as_on, age = ev.ages[0]
        if match.dob_fits_age(new, age, as_on):
            return _done(req, "APPROVE", f"Voter ID {epic} {in_roll} shows age {age} as on {match.fmt_date(as_on)} and requested DOB {match.fmt_date(new)} is within that year and {change}",
                         flags=["Voter ID age range"], **base)
        return _done(req, "REJECT", f"Voter ID {epic} shows age {age} as on {match.fmt_date(as_on)} and requested DOB {match.fmt_date(new)} is outside that range",
                     flags=["Outside voter ID age range"], **base)
    if ev.plain_age is not None and ev.dob_found != "exact":
        return _plain_age(req, ev, new, change, f"Voter ID {epic} {in_roll}", base)
    return _dob_check(req, ev, new, ppp, changed, change, f"Voter ID {epic} {in_roll}", base)


def _roll_age(ev):
    """(age, as-on date) of the first live roll entry, or None."""
    live = [r for r in (ev.epic_rows or []) if not r.get("deleted")] or (ev.epic_rows or [])
    if not live:
        return None
    as_on, age = match.parse_date(live[0].get("age_as_on")), live[0].get("age")
    return (int(age), as_on) if as_on and age is not None else None


def _plain_age(req, ev, new, change, name, base):
    """The document gives an age and no date: it is compared with the requested DOB at the date of the roll (one year
    either way, because the date of the age is not stated)."""
    roll = _roll_age(ev)
    if roll is None:
        return _done(req, "HOLD", f"{name} gives age {ev.plain_age} without a date and the roll entry has no age date so officer to check DOB {match.fmt_date(new)}",
                     flags=["Age without date"], **base)
    years = match.age_on(new, roll[1])[0]
    if abs(years - ev.plain_age) <= 1:
        return _done(req, "APPROVE", f"{name} gives age {ev.plain_age} and requested DOB {match.fmt_date(new)} gives age {years} on {match.fmt_date(roll[1])} and {change}",
                     flags=["Age matches"], **base)
    return _done(req, "HOLD", f"{name} gives age {ev.plain_age} without a date and requested DOB {match.fmt_date(new)} gives age {years} on {match.fmt_date(roll[1])} so officer to read the card",
                 flags=["Age differs, date unknown"], **base)


def _roll_certificate(req, ev, new, base):
    """Electoral roll certificate (officer's rule 5): the certificate must agree with the roll entry of its EPIC."""
    diary = f" diary no {remark.clean(ev.diary)}" if ev.diary else ""
    epic = remark.clean(ev.epic_text or get(req.user_info, "Document Number"))
    shown = match.fmt_date
    if not ev.epic_rows:
        return _done(req, "HOLD", f"EPIC {epic} not found in electoral roll so electoral roll certificate{diary} sent to Election office for verification",
                     flags=["EPIC not in roll"], analysis="EPIC of the certificate is not in the roll", **base)
    live = [r for r in ev.epic_rows if not r.get("deleted")] or ev.epic_rows
    roll = live[0]
    roll_as_on = match.parse_date(roll.get("age_as_on"))
    roll_age = roll.get("age")
    if roll_as_on is None or roll_age is None:
        return _done(req, "HOLD", f"Roll entry of EPIC {epic} has no age so electoral roll certificate{diary} sent to Election office for verification",
                     flags=["Roll entry incomplete"], **base)
    roll_range = f"roll age {roll_age} as on {shown(roll_as_on)}"
    if ev.ages:
        as_on, age = ev.ages[0]
        agrees = age == roll_age or match.dob_fits_age(new, age, as_on) and abs((as_on - roll_as_on).days) < 400 and abs(age - roll_age) <= 1
        fits = match.dob_fits_age(new, age, as_on)
        said = f"age {age} as on {shown(as_on)}"
    elif ev.plain_age is not None:
        # the certificate gives its age at its own date, some time after the roll date: the age may have grown since
        age = ev.plain_age
        today = date.today()
        grown = today.year - roll_as_on.year + 1
        agrees = roll_age - 1 <= age <= roll_age + grown
        low, high = match.age_on(new, roll_as_on)[0], match.age_on(new, today)[0]
        fits = low - 1 <= age <= high + 1
        said = f"age {age}"
    elif ev.dob_dates:
        doc = sorted(ev.dob_dates)[0]
        agrees, fits, said = match.dob_fits_age(doc, roll_age, roll_as_on), doc == new, f"DOB {shown(doc)}"
    else:
        return _done(req, "HOLD", f"Electoral roll certificate{diary} age or DOB could not be read so sent to Election office for verification",
                     flags=["Certificate DOB not read"], **base)
    if agrees and fits:
        return _done(req, "APPROVE", f"Electoral roll certificate{diary} EPIC {epic} verified in electoral roll shows {said} which agrees with {roll_range} and requested DOB {shown(new)}",
                     flags=["Roll certificate agrees with roll"], **base)
    return _done(req, "REJECT", f"Electoral roll certificate{diary} EPIC {epic} shows {said} but {roll_range} and requested DOB {shown(new)} do not agree",
                 flags=["Roll certificate differs from roll"], **base)


def _birth_record(req, ev, new, change, base):
    """The official birth record read through the QR: DOB must equal the requested DOB; name and parents must belong to the
    applicant (both parents differing = another person, father alone = HOLD, mother alone = note)."""
    rec, ui = ev.birth_record, req.user_info
    shown = match.fmt_date
    vtext = "Official birth record"
    if rec["dob"] != new:
        return _done(req, "REJECT", f"Birth certificate verified through QR on official CRS portal shows DOB {shown(rec['dob'])} but requested DOB is {shown(new)}",
                     flags=["Birth record DOB differs"], verification_status="failed", verification_text=vtext + " DOB differs", **base)

    def status(record_value, request_value):
        return match.name_match(record_value, request_value) if record_value and request_value else "missing"

    ok = lambda s: s in ("exact", "close", "partial")
    name_s = status(rec.get("name"), get(ui, "Name"))
    father_s = status(rec.get("father"), get(ui, "Father Name"))
    mother_s = status(rec.get("mother"), get(ui, "Mother Name"))
    notes, flags = [], ["Birth record verified"]
    if father_s == "none" and mother_s == "none":
        if ok(name_s):
            return _done(req, "HOLD", "Birth certificate verified through QR shows DOB same as requested but both parents differ from the request so officer to check",
                         flags=["Both parents differ"], verification_status="verified", verification_text=vtext, **base)
        return _done(req, "REJECT", "Birth certificate verified through QR shows name and both parents different from the applicant so certificate does not belong to the applicant",
                     flags=["Certificate not of applicant"], verification_status="failed", verification_text=vtext + " is of another person", **base)
    if father_s == "none":
        return _done(req, "HOLD", f"Birth certificate verified through QR shows DOB {shown(new)} same as requested but father name {remark.clean(rec.get('father'))} differs from request so officer to check",
                     flags=["Father differs"], verification_status="verified", verification_text=vtext, **base)
    if mother_s == "none":
        notes.append(f"mother name {remark.clean(rec.get('mother'))} differs from request")
        flags.append("Mother differs")
    if name_s == "none":
        notes.append(f"name {remark.clean(rec.get('name'))} differs from request")
        flags.append("Name differs")
    extra = (" but " + " and ".join(notes)) if notes else ""
    return _done(req, "APPROVE", f"Birth certificate Reg No {remark.clean(rec.get('reg_no'))} verified through QR on official CRS portal shows DOB {shown(rec['dob'])} same as requested DOB{extra} and {change}",
                 flags=flags, verification_status="verified", verification_text=vtext, **base)


def _birth(req, ev, new, ppp, changed, change, base):
    if ev.qr_kind == "fake_host":
        return _done(req, "REJECT", f"QR points to non official site {remark.clean(ev.qr_host)} so birth certificate is not genuine",
                     flags=["Fake QR"], verification_status="failed", verification_text=f"QR host {ev.qr_host}", **base)
    if ev.birth_record:
        return _birth_record(req, ev, new, change, base)
    if ev.qr_kind == "official" and qr.host_allowed(ev.qr_host):
        # a site the analyser has a verifier for must be opened; until the record is read the certificate is not accepted
        return _done(req, "HOLD", "Birth certificate QR points to the official portal but the record could not be read so DCRIM to verify the certificate",
                     flags=["Birth record not read"], **base)
    if ev.qr_kind == "official":
        if ev.qr_opened:
            return _done(req, "HOLD", "Official birth record could not be read so DCRIM to verify the certificate", flags=["Birth record unreadable"], **base)
        if ev.dob_found == "exact":
            return _done(req, "APPROVE", f"QR of birth certificate points to official government site and record was not opened and certificate shows DOB {match.fmt_date(new)} same as requested DOB",
                         flags=["Gov site not opened"], **base)
        return _done(req, "HOLD", "QR of birth certificate points to a government site that was not opened and DOB was not read from the certificate so officer to verify",
                     flags=["Gov site not opened"], **base)
    if ev.qr_kind in ("plain_text", "court_case", "mcd_text"):
        return _done(req, "HOLD", "Birth certificate QR carries no government link so DCRIM to verify the certificate", flags=["QR not verifiable"], **base)
    # no readable QR
    if ev.dob_found == "exact" and new.year >= 2000:  # officer's rule 27 10 2026: the certificate's own DOB is enough from 2000
        if ppp != new:  # officer's rule 28 10 2026: only when the PPP DOB is the requested DOB, else HOLD
            return _done(req, "HOLD", f"Birth certificate QR is unreadable and certificate shows DOB {match.fmt_date(new)} same as requested DOB but PPP DOB is {match.fmt_date(ppp) if ppp else 'not available'} so officer to review the change",
                         flags=["QR unreadable, PPP DOB changed"], **base)
        return _done(req, "APPROVE", f"Birth certificate QR is unreadable but certificate shows DOB {match.fmt_date(new)} same as requested DOB of year 2000 or later and {change}",
                     flags=["QR unreadable, DOB read from certificate"], **base)
    if ev.issuer == "haryana":
        return _done(req, "REJECT", "QR is unreadable Applicant to visit the office of ADC with the original document", flags=["QR unreadable"], **base)
    return _done(req, "HOLD", "Birth certificate has no readable QR so officer to review", flags=["No QR"], **base)


# ---------------------------------------------------------------------------------------------------------
RETRY_CLASSES = (BOARD, SLC, SCHOOL, PASSPORT, GOVT_ID, "unknown")


def _retry_with_variants(text, new, variant_texts):
    """When the requested date was not found, read the document again in other ways (see vision_ocr.VARIANTS) until it is.
    `variant_texts` yields texts lazily.  Returns (found, text) where text includes the variant that found it."""
    found = dobtext.find_dob(text, new)
    if found == "exact":
        return found, text
    for extra in variant_texts:
        if dobtext.find_dob(extra, new) == "exact":
            return "exact", text + "\n" + extra
    return found, text


def _pages(pdf_path):
    try:
        import pypdf
        return len(pypdf.PdfReader(str(pdf_path)).pages)
    except Exception:
        return None


HARYANA_PLACES = ("haryana", "palwal", "faridabad", "gurugram", "gurgaon", "nuh", "mewat", "rohtak", "sonipat", "sonepat",
                  "hisar", "bhiwani", "jhajjar", "rewari", "mahendragarh", "narnaul", "karnal", "panipat", "kurukshetra",
                  "kaithal", "jind", "sirsa", "ambala", "panchkula", "yamunanagar", "fatehabad", "charkhi dadri", "hodal",
                  "hathin", "hassanpur", "prithla", "bahadurgarh", "ballabgarh",
                  "हरियाणा", "पलवल", "फरीदाबाद", "गुरुग्राम", "गुड़गांव", "नूंह", "मेवात", "रोहतक", "सोनीपत", "हिसार", "भिवानी",
                  "झज्जर", "रेवाड़ी", "महेंद्रगढ़", "करनाल", "पानीपत", "कुरुक्षेत्र", "कैथल", "जींद", "सिरसा", "अंबाला", "पंचकूला",
                  "यमुनानगर", "फतेहाबाद", "चरखी दादरी", "होडल", "हथीन", "बल्लभगढ़")


def _school_state(text):
    t = (text or "").lower()
    if any((re.search(rf"\b{re.escape(place)}\b", t) if place.isascii() else place in t) for place in HARYANA_PLACES):
        return "haryana"
    return "other" if any(state in t for state in OTHER_STATES) else "unknown"


def _birth_record_of(link, verifier=None):
    """Official CRS birth record as a dict, or None when the page could not be read."""
    from datetime import date as _date

    if verifier is None:
        from .verify import crs_birth
        verifier = crs_birth.verify
    rec = verifier(re.search(r"https?://[^\s|\"'<>]+", link).group(0))
    if rec.status != "verified":
        return None
    f = rec.fields
    try:
        dob = _date.fromisoformat(f["dob"])
    except (KeyError, ValueError):
        return None
    return {"dob": dob, "name": f.get("name", ""), "father": f.get("father", ""), "mother": f.get("mother", ""),
            "reg_no": f.get("reg_no", ""), "unit": f.get("unit", "")}


def gather(req):
    """Evidence from the request's PDF (Apple Vision text plus the cached tesseract text, QR, electoral roll)."""
    from . import ocr, vision_ocr

    ui = req.user_info
    new = match.parse_date(get(ui, "Requested DOB"))
    label = get(ui, "Uploaded Document")
    if not req.pdf_path:
        return Evidence(doc_class="none", readable=False)
    parts = []
    if vision_ocr.available():
        parts.append(vision_ocr.text_of(req.pdf_path))
    try:
        parts.append(ocr.text_of(req.pdf_path)[0])
    except Exception:
        pass
    text = "\n".join(parts)
    ev = Evidence(doc_class=classify_text(text, label), readable=len(re.findall(r"\w+", text)) >= 30)
    if ev.doc_class in RETRY_CLASSES and vision_ocr.available():
        variants = (vision_ocr.variant_text(req.pdf_path, n, d, a) for n, d, a in vision_ocr.VARIANTS)
        ev.dob_found, text = _retry_with_variants(text, new, variants)
    else:
        ev.dob_found = dobtext.find_dob(text, new)
    ev.ppp_shown = dobtext.find_dob(text, match.parse_date(get(ui, "DOB In PPP"))) == "exact"
    ev.ages = dobtext.ages_as_on(text)
    plain = dobtext.plain_ages(text)
    ev.plain_age = plain[0] if plain else None
    ev.dob_dates, ev.dob_years = dobtext.dob_context(text, same_line=ev.doc_class in (VOTER, ROLL_CERT))
    if ev.doc_class in (VOTER, ROLL_CERT):
        ev.epic_text = get(ui, "Document Number")
        ev.epic_rows = electors.lookup(ev.epic_text)
    if ev.doc_class == SLC:
        pages = _pages(req.pdf_path)
        ev.register_copy = bool((pages or 0) >= 2 or re.search(r"register", text, re.I) or "copy of school record" in label.lower())
        ev.school_state = _school_state(text)
    ev.discharge_dob = match.parse_date(get(ui, "Date of Birth (Discharge Certificate)"))
    link = qr.best_link(qr.decode_pdf(req.pdf_path))
    if link:
        ev.qr_kind, ev.qr_host = qr.classify(link)
        if ev.doc_class == BIRTH and ev.qr_host in ("dc.crsorgi.gov.in", "crsorgi.gov.in"):
            ev.birth_record = _birth_record_of(link)
    elif ev.doc_class == BIRTH:
        from . import issuer as issuer_mod
        ev.issuer = issuer_mod.issuer_of(req.pdf_path)[0]
    return ev
