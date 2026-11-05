"""Decision rules for Marital Tagging (docs/RULES.md).

analyse(request, ...) -> Decision.  Dependencies are injectable so the rules can be tested on synthetic data:
  payloads(request) -> list of QR strings                    (default: qr.decode_pdf, cached)
  verifiers         -> {"crs": f(url), "ndmc": f(url), "mcd": f(qr_text)} each returning verify.base.Record
  issuer(request)   -> (state, read_by, note)                (default: issuer.issuer_of on the PDF)
  text_of(request)  -> (text, info) of a divorce decree      (default: ocr.text_of)

Widow / Widower: the death certificate is verified through its QR on the official site and the deceased is linked to the
applicant (the certificate names the applicant, or - when it shows no spouse - the deceased's name and father match the request).
Divorced uses the decree engine (rules_divorce).  Married and the correction back to Unmarried wait for the officer.
"""
import re

from . import match, qr, remark, rules_divorce
from .load import Request, get, norm
from .rules_marriage import Decision, _done, _family_rows, _find_row

CRS_HOSTS = ("crsorgi.gov.in", "dc.crsorgi.gov.in")
NDMC_HOSTS = ("bnd.ndmc.gov.in",)
MCD_HOSTS = ("mcdonline.nic.in",)
SOURCE_NAMES = {"crs": "CRS", "ndmc": "NDMC", "mcd": "MCD"}
QR_UNREADABLE = "QR is unreadable Applicant to visit the office of ADC with the original document"
ROLE = {"widow": ("husband", "Widow", "wife", "m"), "widower": ("wife", "Widower", "husband", "f")}


def _default_verifiers():
    from .verify import crs, mcd, ndmc
    return {"crs": crs.verify, "ndmc": ndmc.verify, "mcd": mcd.verify}


def analyse(req, payloads=None, verifiers=None, issuer=None, text_of=None, marriage_verifier=None):
    kind = norm(req.request_type)
    if kind == "divorced":
        return rules_divorce.analyse(req, text_of=text_of)
    ui = req.user_info
    name = get(ui, "Name") or req.name
    facts = [["Request", f"{get(ui, 'Current Status In PPP') or '-'} to {req.request_type}"], ["Applicant", name],
             ["Spouse (deceased) per request", get(ui, "Spouse Full Name")], ["Spouse father per request", get(ui, "Spouse Father Name")],
             ["Date of death per request", get(ui, "Date Of Death")], ["Certificate number per request", get(ui, "Death Certificate Number")],
             ["Issuing authority per request", get(ui, "Issuing Authority")]]

    def done(rec, body, flags, analysis, status="na", vtext=""):
        return _done(req, rec, body, flags=flags, facts=facts, analysis=analysis, verification_status=status, verification_text=vtext)

    if kind == "unmarried":
        return done("HOLD", "Correction back to Unmarried needs the officer to decide", ["Unmarried correction"],
                    "Correction back to Unmarried waits for an officer rule")
    if kind == "married":
        return _married(req, payloads, issuer, marriage_verifier)
    if kind not in ROLE:
        return done("HOLD", f"Requested status {remark.clean(req.request_type) or 'blank'} is not covered by the rules so officer to review",
                    ["Status not covered"], "Requested status not covered")

    payloads = payloads or (lambda r: qr.decode_pdf(r.pdf_path) if r.pdf_path else [])
    link = qr.best_link(payloads(req) or [])
    if link is None:
        if issuer is None:
            from . import issuer as issuer_mod
            issuer = lambda r: issuer_mod.issuer_of(r.pdf_path) if r.pdf_path else ("unknown", "-", "")
        state = issuer(req)[0]
        if state == "haryana":
            return done("REJECT", QR_UNREADABLE, ["QR unreadable"],
                        "No readable QR; certificate issued by Government of Haryana, which provides QR based documents")
        why = {"unknown": "issuer not readable", "mixed": "issuer unclear", "non government": "issued by a society or is an agreement"}.get(state, f"issued by {state}")
        return done("HOLD", f"No QR found and certificate {why} so officer to review", ["No QR"], f"No readable QR; {why}")

    qkind, host = qr.classify(link)
    if qkind == "fake_host":
        return done("REJECT", f"QR points to non official site {remark.clean(host)} so certificate is not genuine", ["Fake QR"],
                    "QR points to a non government host", "failed", f"QR host {host}")
    if qkind in ("plain_text", "court_case"):
        return done("HOLD", "QR holds only a number or text with no verification link so DCRIM to verify the certificate",
                    ["QR not verifiable"], "QR is plain text or a bare number")

    verifiers = {**_default_verifiers(), **(verifiers or {})}
    url = re.search(r"https?://[^\s|\"'<>]+", link).group(0)
    if host in CRS_HOSTS:
        rec = verifiers["crs"](url)
    elif host in NDMC_HOSTS:
        rec = verifiers["ndmc"](url)
    elif qkind == "mcd_text" or host in MCD_HOSTS:
        rec = verifiers["mcd"](link)
    else:
        note = f"QR points to official government site {remark.clean(host)} and record was not opened so decided on PPP data"
        if not get(ui, "Spouse Full Name"):
            return done("HOLD", f"{note} but spouse name is blank on request so officer to review", ["Site not opened", "Spouse blank"],
                        "Government QR not opened and no spouse named on the request")
        return done("APPROVE", f"{note} so status {ROLE[kind][1]}", ["Site not opened"],
                    "Government QR on a site the analyser does not open", "na", f"QR host {host} accepted as government site")

    if rec.status != "verified":
        return done("HOLD", f"Official site did not return the certificate {remark.clean(rec.error)} so DCRIM to verify",
                    ["Site error"], "Official site could not be reached or returned no certificate", "failed", rec.error)
    return _compare(req, rec, kind, name, done, facts)


def _married(req, payloads, issuer, verifier):
    """Married: the marriage certificate is verified through its QR and both parties must be adults (docs/RULES.md).
    The Marriage rules do this check; Marital requests lack the date of marriage and date of birth, which come from the certificate
    and from the applicant's row of the PPP family table."""
    from . import rules_marriage
    ui = dict(req.user_info)
    rows = _family_rows(req, "family") or []
    row = _find_row(rows, get(ui, "Name") or req.name)
    if row and get(row, "Date of Birth") and not get(ui, "Date of Birth"):
        ui["Date of Birth"] = get(row, "Date of Birth")
    raw = {**req.raw, "case": {**req.case, "User Info": ui}, "old_family": req.raw.get("family"), "new_family": req.raw.get("family")}
    shim = Request(req.module, req.folder, raw)
    kw = {"payloads": payloads, "issuer": issuer, "verifier": verifier, "conclusion": "status Married"}
    return rules_marriage.analyse(shim, **{k: v for k, v in kw.items() if v is not None})


def _compare(req, rec, kind, name, done, facts):
    ui = req.user_info
    cert, src = rec.fields, SOURCE_NAMES.get(rec.source, rec.source)
    husband_or_wife, status_word, applicant_is, _ = ROLE[kind]
    dod = match.parse_date(cert.get("dod"))
    cname = cert.get("name", "")
    reg = remark.clean(cert.get("reg_no"))
    base = (f"Death certificate Reg No {reg} of {husband_or_wife} {remark.clean(cname)} died {match.fmt_date(dod)}"
            + (f" issued by {remark.clean(cert['unit'])}" if cert.get("unit") else "")
            + f" verified through QR on official {src} portal")
    vt = f"{src} record: {cname}, died {match.fmt_date(dod)}" + (f", {cert['spouse']} named as spouse" if cert.get("spouse") else "")
    facts += [["Certificate name", cname], ["Certificate date of death", match.fmt_date(dod)], ["Certificate father", cert.get("father", "")],
              ["Certificate spouse", cert.get("spouse", "")], ["Certificate registration", f"{cert.get('reg_no', '')} {cert.get('unit', '')}".strip()]]

    spouse = get(ui, "Spouse Full Name")
    rows = _family_rows(req, "family") or []
    arow = _find_row(rows, name)
    if not spouse and arow:
        spouse = get(arow, "Spouse Name")
    sp_father = get(ui, "Spouse Father Name")
    rejects, holds, notes, flags = [], [], [], []

    rdod = match.parse_date(get(ui, "Date Of Death"))
    dod_agrees = bool(dod and rdod and dod == rdod)

    # 1. is this the deceased the request names?
    name_rank = match.name_match(spouse, cname) if spouse else "missing"
    if spouse and cname and name_rank == "missing":
        notes.append("name on certificate could not be compared by machine")  # e.g. written in Hindi
        flags.append("Name not compared")
    elif spouse and name_rank == "none":
        if dod_agrees and match.one_letter_variant(spouse, cname):
            notes.append(f"deceased name spelled {remark.clean(cname)} on certificate and {remark.clean(spouse)} on request")
            flags.append("Name spelling")
        else:
            return done("REJECT", f"{base} but names {remark.clean(cname)} and not {husband_or_wife} {remark.clean(spouse)} of the request "
                        "so apply again with the correct certificate", ["Deceased differs"], "Certificate is of another person", "verified", vt)
    name_strong = name_rank in ("exact", "close")

    # 2. is the deceased linked to the applicant?
    cert_spouse = cert.get("spouse")
    if cert_spouse and not match.acceptable(name, cert_spouse) and any(
            cert.get(k) and match.acceptable(cert_spouse, cert[k]) for k in ("mother", "father")):
        # NDMC often shows the deceased's own parent in the Husband/Wife field: that is a site quirk, not a different spouse
        cert_spouse = None
        flags.append("Spouse field repeats parent")
    if cert_spouse:
        if match.acceptable(name, cert_spouse):
            link_text = f"certificate names applicant {remark.clean(name)} as {applicant_is}"
        else:
            return done("REJECT", f"{base} and names {applicant_is} as {remark.clean(cert_spouse)} and not applicant {remark.clean(name)} "
                        "so apply again after correction of the certificate or with proof that both names are of the same person",
                        ["Different spouse"], "Official record names a different spouse", "verified", vt)
    else:
        if not spouse:
            body = f"{base} but request names no spouse and certificate shows none so nothing links the deceased to applicant {remark.clean(name)}"
            if norm(get(ui, "Current Status In PPP")) == "unmarried":
                return done("REJECT", body + " so apply again with proof of marriage", ["No link"], "Nothing links the applicant to the deceased", "verified", vt)
            return done("HOLD", body + " so officer to review", ["No link"], "Nothing links the applicant to the deceased", "verified", vt)
        cfather, cmother = cert.get("father"), cert.get("mother")
        if sp_father and (cfather or cmother):
            if cfather and match.acceptable(sp_father, cfather):
                link_text = f"deceased name and father {remark.clean(cfather)} match the spouse details of applicant {remark.clean(name)}"
            elif cmother and match.acceptable(sp_father, cmother):
                # CRS records show the request's father name in the mother field in many cases: the parent name matches
                link_text = f"deceased name and parent name {remark.clean(cmother)} match the spouse details of applicant {remark.clean(name)}"
                flags.append("Father in mother field")
            elif name_strong and dod_agrees:
                link_text = f"deceased name and date of death match the spouse details of applicant {remark.clean(name)}"
                notes.append(f"father {remark.clean(sp_father)} on request differs from {remark.clean(cfather or cmother)} on certificate")
                flags.append("Father differs")
            else:
                holds.append(f"father on certificate {remark.clean(cfather or cmother)} differs from spouse father {remark.clean(sp_father)} on request")
                flags.append("Father differs")
                link_text = ""
        else:
            link_text = f"deceased name matches the spouse of applicant {remark.clean(name)} and father was not compared"
            notes.append("father of deceased not compared")
            flags.append("Father not compared")

    # 3. date of death, gender, kind of record
    if cert.get("activity") and "death" not in cert["activity"].lower():
        holds.append(f"record is of type {remark.clean(cert['activity'])} and not a death record")
        flags.append("Not a death record")
    if dod and rdod and dod != rdod:
        holds.append(f"date of death on request {match.fmt_date(rdod)} differs from certificate {match.fmt_date(dod)}")
        flags.append("Date mismatch")
    gender = norm(cert.get("gender"))[:1]
    want = ROLE[kind][3]
    if gender in ("m", "f") and gender != want:
        holds.append(f"certificate gender is {'male' if gender == 'm' else 'female'} but status asked is {status_word}")
        flags.append("Gender differs")
    rno = norm(get(ui, "Death Certificate Number"))
    if rno and cert.get("reg_no") and rno.replace(" ", "") != norm(cert["reg_no"]).replace(" ", ""):
        flags.append("Number differs")  # NDMC online numbers differ from old numbers: noted, never a reason by itself

    analysis = "; ".join(holds + notes) or "Certificate verified; deceased, link to applicant and date of death agree"
    if holds:
        return done("HOLD", f"{base} but " + " and ".join(holds) + " so officer to review", flags, analysis, "verified", vt)
    return done("APPROVE", f"{base} and {link_text} so status {status_word}" + "".join(" " + n for n in notes), flags, analysis, "verified", vt)
