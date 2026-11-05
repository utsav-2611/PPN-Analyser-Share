# Decision rules

These are the rules the analyser applies, as instructed by the commissioning officer. They are implemented in `analyser/rules_*.py`
and covered by tests. Where a rule cannot be decided from the evidence, the answer is **HOLD** with the reason and who should check it.
The goal is more decisions and fewer holds, never a guess.

## General

- **Official sites only.** A QR link counts as genuine when its host is `gov.in` or `nic.in`, or ends with `.gov.in` / `.nic.in`. Any other
  host, including lookalikes such as `crsorgi.gov.in.evil.com`, is fake: **REJECT**, "QR points to non official site <host>". The analyser
  *opens* a link only when its host has a checker (`rules.yaml`, `allowed_hosts`). A genuine government QR whose site has no checker is accepted
  as genuine and is not put on HOLD for that reason.
- **No readable QR / no QR** (death or marriage certificate; decrees are judged by their text): the issuing state is read from the certificate.
  Issued by the **Government of Haryana**: REJECT, "QR is unreadable Applicant to visit the office of ADC with the original document".
  Anything else (another state, unreadable issuer, a society or affidavit): HOLD for the officer.
- **QR on a government site the analyser cannot open** (for example Punjab, Uttarakhand, Himachal, Gujarat portals): APPROVE on the PPP data and the
  subordinates' remarks; the remark says the record was not opened. A bare-number or DigiLocker QR: HOLD for DCRIM to verify.
- **Names:** a partial match (missing surname or initials) counts as a match when linking people.
- **LLY (Lado Lakshmi Yojana) and priority requests** get exactly the same checks; they are only listed first.
- Note, but do not block on, PPP data errors (a default date of birth of 01 01 1990, children recorded as grandchildren and similar).

## Remarks

`<Approved|Rejected|On hold> <document, number, date, issuing office> <how it was verified> <the facts that decide it> <conclusion>
<subordinate basis>`. Letters, digits and spaces only, at most 500 characters, dates as `25 10 2025`. The subordinate basis (ZCRIM / DCRIM / FCP
with name, date and "on basis of uploaded document") is shortened first when the remark is too long.

## Marriage / Divorce PPN update

- **Marriage.** Age on the date of marriage: bride under 18 or groom under 21 is REJECT (exact years and months). Certificate verified on the official
  site, names and parents match, ages fine: APPROVE. Marriage outside Haryana is treated the same, with the flag "Outside Haryana".
  - Date of marriage on the request differs from the certificate: HOLD, both dates in the reason.
  - The PPP already shows a different spouse: HOLD, with both names.
  - Parents (applicant from the request, spouse from the PPP family table) against the certificate: father differs, HOLD; both parents differ, REJECT
    (certificate is of someone else); mother only differs, APPROVE with a note.
  - A child of the couple conceived while the bride was under 18: HOLD, "possibility of marriage while minor needs examination".
  - Applicant to be moved is not in the family: REJECT. Family table not captured: APPROVE if verified, "confirm on portal".
  - Delhi eDistrict certificate (QR is plain text): decided on the QR text, name and date compared; remark says it was not verified online.
- **Divorce.** The document must be a decree dissolving the marriage (not a criminal judgement, agreement, notice, appeal or adjournment order); the parties
  must match the applicant and spouse; the remark states who has custody. Children move with the parent who has custody; a request that moves them
  otherwise is REJECT. A decree that cannot be classified or read is HOLD for the officer.

## Marital tagging

- **Widow / Widower.** Death certificate verified through its QR (CRS, NDMC, MCD) and the deceased linked to the applicant: spouse named on the
  certificate, or (spouse blank) the PPP spouse name and the deceased's father match. Verified and linked: APPROVE. A genuine record naming a different
  spouse: REJECT, asking for a corrected certificate or proof of identity.
- **Married:** registered marriage certificate verified; both adults: APPROVE. **Divorced:** decree engine as above.
- **Unmarried to Widow:** APPROVE only with a positive link; otherwise REJECT asking for proof of marriage.
- **Correction back to Unmarried:** HOLD until the officer gives a rule.

## DOB tagging

Accepted documents: voter ID issued 2019 or earlier, matriculation / secondary / middle school board certificate, School Leaving Certificate,
passport, government ID card (armed forces discharge certificate), birth certificate verified through its QR, electoral roll certificate.

- **Reading the document.** The requested date is looked for in the text read from the document (offline text recognition). A full date that is readable
  must match completely. If the date is not readable but the year is, the year must match (APPROVE with a note). If a single full date is readable on the
  date-of-birth line and differs, REJECT. If a date is one digit away from the requested one, or several dates are present, or nothing can be read: HOLD.
- **Board certificate, passport, government ID:** as above. **Armed forces discharge certificate:** its date of birth must equal the requested date.
- **School Leaving Certificate.** It must be accompanied by a copy of the school entry exit register (present, readable or not); without it: REJECT, asking the applicant to upload it. From a school in
  **Haryana** it is accepted for any change of date. From a school **outside Haryana**, a change of more than two years from the PPP date is REJECT. When the
  state cannot be read and the change exceeds two years, HOLD.
- **Voter ID.** The EPIC is checked against the electoral roll (leading zero of the last number added or removed, slashes and spaces ignored).
  An EPIC **not in the roll is REJECT**. Issued after 2019 is REJECT (applied when the issue year can be read from the card). If the card gives "age as on <date>", the requested date of birth must fall in the one-year
  range before that date (otherwise REJECT). A card that gives an age with no date is compared with the roll's date, one year either way; a mismatch is HOLD.
- **Electoral roll certificate.** The EPIC is checked against the roll. The certificate agrees with the roll (age, allowing for the years since the roll
  date) and with the requested date: APPROVE. It differs: REJECT. EPIC not in the roll: HOLD, sent to the Election office for verification.
- **Birth certificate.** Fake QR host: REJECT. A QR on the official CRS portal: the record is read and its date of birth must equal the requested date
  (REJECT if not); name and parents are compared (both parents and name differ, REJECT; both parents differ with the name matching, or father only, HOLD; mother
  only or name only, APPROVE with a note). If the record cannot be read, HOLD for DCRIM. No readable QR: APPROVE when the date of birth read from the certificate equals the requested date and that date is in the year 2000 or later (any issuing state); otherwise REJECT if issued by Haryana, else HOLD.
- **No document uploaded:** REJECT.
