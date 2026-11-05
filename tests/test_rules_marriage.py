import unittest

from analyser import remark, rules_marriage as rm
from analyser.load import Request
from analyser.verify.base import Record

ULB = "http://edisha.gov.in/Default_VerifyCertificate.aspx?tid=1&cid=2&aid=5"
CERT = {"marriage_date": "2024-03-07", "place": "Town", "bride_name": "Sita Devi", "bride_dob": "2002-06-05",
        "bride_father": "Ram Lal", "bride_mother": "Gita", "groom_name": "Mohan Lal", "groom_dob": "1999-05-01",
        "groom_father": "Hari Lal", "groom_mother": "Rani", "reg_no": "59", "reg_date": "2024-03-27",
        "issued_by": "Sub Registrar Ballabgarh"}
INFO = {"Name": "Sita Devi", "Father Name": "Ram Lal", "Mother Name": "Gita", "Date of Birth": "05/06/2002",
        "Date Of Marriage": "07/03/2024", "Spouse Full Name": "Mohan Lal", "Place of Marriage": "Haryana"}
FAM = [{"Full Name": "Sita Devi", "Spouse Name": "", "Gender": "Female"}]


def make(info=None, old=FAM, new=FAM, subs=True):
    raw = {"request_id": "1", "list_row": {"Request Type": "Marriage", "FamilyID": "F1"},
           "case": {"User Info": {**INFO, **(info or {})}}, "old_family": old, "new_family": new}
    if subs:
        raw["ZCRIM Remark (Ajay Singh)"] = {"Status": "Forwarded", "Action Date": "11-03-2026"}
    return Request("marriage", "/nonexistent", raw)


def run(req=None, cert=None, link=ULB, status="verified", **kw):
    rec = Record("edisha", status, fields={**CERT, **(cert or {})}, error="" if status == "verified" else "curl exit 7")
    d = rm.analyse(req or make(), payloads=lambda r: [link] if link else [], verifier=lambda u: rec, **kw)
    assert remark.valid(d.remark), d.remark
    return d


class Marriage(unittest.TestCase):
    def test_clean_approve(self):
        d = run()
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("Reg No 59", d.remark)
        self.assertIn("bride aged 21 years 9 months", d.remark)
        self.assertIn("ZCRIM Ajay Singh forwarded on 11 03 2026", d.remark)

    def test_underage_bride_rejected(self):
        d = run(cert={"bride_dob": "2006-03-08"}, req=make({"Date of Birth": "08/03/2006"}))
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("17 years 11 months", d.remark)

    def test_underage_groom_rejected(self):
        d = run(cert={"groom_dob": "2003-03-08"})
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("groom", d.remark)

    def test_date_mismatch_holds(self):
        d = run(req=make({"Date Of Marriage": "09/03/2024"}))
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("Date mismatch", d.flags)

    def test_applicant_not_on_certificate(self):
        self.assertEqual(run(req=make({"Name": "Geeta Kumari"})).recommendation, "REJECT")

    def test_partial_name_counts_as_match(self):
        self.assertEqual(run(req=make({"Name": "Sita"})).recommendation, "APPROVE")

    def test_both_parents_differ_rejects_one_differs_holds(self):
        self.assertEqual(run(req=make({"Father Name": "Om Prakash", "Mother Name": "Kamla"})).recommendation, "REJECT")
        self.assertEqual(run(req=make({"Father Name": "Om Prakash"})).recommendation, "HOLD")

    def test_spouse_differs_rejects(self):
        self.assertEqual(run(req=make({"Spouse Full Name": "Ravi Kumar"})).recommendation, "REJECT")

    def test_not_in_family_and_married_in_ppp(self):
        self.assertEqual(run(req=make(old=[{"Full Name": "Other Person"}])).recommendation, "REJECT")
        d = run(req=make(old=[{"Full Name": "Sita Devi", "Spouse Name": "Ravi Kumar"}]))
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("Married in PPP", d.flags)
        self.assertIn("PPP already shows spouse Ravi Kumar", d.remark)

    def test_family_not_captured_and_outside_haryana_flags(self):
        d = run(req=make({"Place of Marriage": "OutSideHaryana"}, new=None))
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("Confirm on portal", d.flags)
        self.assertIn("Outside Haryana", d.flags)

    def test_spouse_row_father_differs_holds(self):
        husband = {"Name": "Mohan Lal", "Father Name": "Hari Lal", "Mother Name": "Rani", "Date of Birth": "01/05/1999",
                   "Spouse Full Name": "Sita Devi"}
        wife_row = {"Full Name": "Sita Devi", "Father Name": "Pappan", "Mother Name": "Gita"}
        d = run(req=make(husband, old=[{"Full Name": "Mohan Lal"}], new=[wife_row]))
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("Spouse parent mismatch", d.flags)
        self.assertIn("Ram Lal", d.remark)       # father named on the certificate

    def test_mother_only_difference_is_a_note(self):
        d = run(req=make({"Mother Name": "Kamla"}))
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("Mother differs", d.flags)
        d = run(req=make({"Father Name": "Om Prakash"}))
        self.assertEqual(d.recommendation, "HOLD")

    def test_igr_verified_is_decided_on_request_data(self):
        rec = Record("igr", "verified", text="marathi text")
        d = rm.analyse(make(), payloads=lambda r: ["https://adjudication.igrmaharashtra.gov.in/eMarriage2.0/marriage/view-cert-qr/abc"],
                       igr_verifier=lambda u: rec)
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("Names not machine checked", d.flags)
        failed = Record("igr", "failed", error="curl exit 7")
        d = rm.analyse(make(), payloads=lambda r: ["https://adjudication.igrmaharashtra.gov.in/x"], igr_verifier=lambda u: failed)
        self.assertEqual(d.recommendation, "HOLD")

    def test_spouse_row_both_parents_differ_rejects(self):
        husband = {"Name": "Mohan Lal", "Father Name": "Hari Lal", "Mother Name": "Rani", "Date of Birth": "01/05/1999",
                   "Spouse Full Name": "Sita Devi"}
        wife_row = {"Full Name": "Sita Devi", "Father Name": "Pappan", "Mother Name": "Kamla"}
        d = run(req=make(husband, old=[{"Full Name": "Mohan Lal"}], new=[wife_row]))
        self.assertEqual(d.recommendation, "REJECT")

    def test_child_conceived_while_bride_minor_holds(self):
        # bride born 05/06/2002 turns 18 on 05/06/2020; child born 10/11/2020 was conceived at 17
        kids = FAM + [{"Full Name": "Child One", "Mother Name": "Sita Devi", "Father Name": "Mohan Lal", "Date of Birth": "10/11/2020"}]
        d = run(req=make(new=kids))
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("Child before 18", d.flags)
        self.assertIn("possibility of marriage while minor", d.remark)

    def test_child_after_bride_turned_18_is_fine(self):
        kids = FAM + [{"Full Name": "Child One", "Mother Name": "Sita Devi", "Father Name": "Mohan Lal", "Date of Birth": "10/11/2022"},
                      {"Full Name": "Other", "Mother Name": "Someone Else", "Father Name": "Mohan Lal", "Date of Birth": "10/11/2010"}]
        self.assertEqual(run(req=make(new=kids)).recommendation, "APPROVE")

    def test_empty_placeholder_family_row_is_not_captured(self):
        d = run(req=make(old=[{"": "", "Full Name": "", "S.No": ""}], new=[{"Full Name": ""}]))
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("Confirm on portal", d.flags)
        self.assertNotIn("Not in family", d.flags)

    def test_dob_differs_but_not_underage_is_note(self):
        d = run(req=make({"Date of Birth": "05/06/2001"}))
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("DOB differs", d.flags)

    def test_site_error_holds(self):
        self.assertEqual(run(status="failed").recommendation, "HOLD")

    def test_fake_host_rejected(self):
        d = run(link="http://crsorgi.gov.in.evil.com/a?x=1")
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("non official site", d.remark)


PEH = {"marriage_date": "2024-03-07", "reg_no": "9 / 9", "reg_date": "2024-03-27", "bride_name": "Sita Devi",
       "bride_father": "Ram Lal", "groom_name": "Mohan Lal", "groom_father": "Hari Lal"}
PEH_LINK = "http://pehchan.rajasthan.gov.in/rpt_qrcode.aspx?param=abc"


def run_peh(req=None, cert=None):
    rec = Record("pehchan", "verified", fields={**PEH, **(cert or {})})
    return rm.analyse(req or make(), payloads=lambda r: [PEH_LINK], verifier=lambda u: rec)


class Pehchan(unittest.TestCase):
    def test_parse(self):
        from analyser.verify import pehchan
        text = """Registration No.:
12 / 2024
Registration Date:
27/03/2024
Date of Marriage:
07/03/2024
Groom Name:
Mohan Lal
Groom's Father Name:
Hari Lal
Bride Name:
Sita Devi
Bride's Father Name:
Ram Lal
Signer's Name/Designation:
Someone, Registrar"""
        f = pehchan.parse_certificate(text)
        self.assertEqual(f["marriage_date"], "2024-03-07")
        self.assertEqual(f["bride_father"], "Ram Lal")
        self.assertEqual(f["groom_name"], "Mohan Lal")
        self.assertEqual(f["reg_no"], "12 / 2024")

    def test_approve_uses_request_and_family_dobs(self):
        fam = [{"Full Name": "Sita Devi", "Spouse Name": ""}, {"Full Name": "Mohan Lal", "Date of Birth": "01/05/1999"}]
        d = run_peh(make(old=fam, new=fam))
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("Pehchan Rajasthan", d.remark)

    def test_underage_from_request_dob(self):
        d = run_peh(make({"Date of Birth": "08/03/2006"}))
        self.assertEqual(d.recommendation, "REJECT")


class OtherQr(unittest.TestCase):
    def test_no_qr_haryana_rejects_with_adc_comment(self):
        d = run(link=None, issuer=lambda r: ("haryana", "ocr", ""))
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("Applicant to visit the office of ADC with the original document", d.remark)

    def test_no_qr_other_state_or_unknown_holds(self):
        for state in ("uttar pradesh", "unknown", "non government"):
            self.assertEqual(run(link=None, issuer=lambda r, s=state: (s, "ocr", "")).recommendation, "HOLD")

    def test_delhi_edistrict_text(self):
        d = run(link="123456|Sita Devi|M|07/03/2024")
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("not verified online", d.remark)
        self.assertEqual(run(link="123456|Other Person|M|07/03/2024").recommendation, "REJECT")
        self.assertEqual(run(link="123456|Sita Devi|M|09/03/2024").recommendation, "HOLD")

    def test_unknown_plain_text_holds(self):
        self.assertEqual(run(link="AB12").recommendation, "HOLD")

    def test_unopened_government_site_approves(self):
        d = run(link="https://esewa.punjab.gov.in/verify?id=1")
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("record was not opened", d.remark)

    def test_unopened_site_applicant_underage_rejects(self):
        d = run(link="https://esewa.punjab.gov.in/verify?id=1", req=make({"Date of Birth": "08/03/2006"}))
        self.assertEqual(d.recommendation, "REJECT")


if __name__ == "__main__":
    unittest.main()
