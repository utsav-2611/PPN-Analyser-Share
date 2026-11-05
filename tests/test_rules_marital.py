import unittest

from analyser import remark, rules_marital as rm
from analyser.load import Request
from analyser.verify.base import Record

CRS = "https://dc.crsorgi.gov.in/crs/verifyCertificate?id=QUJD"
NDMC = "https://bnd.ndmc.gov.in/verify-certificate/abcdef"
MCD = "Name Of The Deceased RAM KUMAR Verified URL: https://mcdonline.nic.in/rbd/x?a=1"
INFO = {"Name": "Sita Devi", "Father Name": "Ram Lal", "Current Status In PPP": "Married", "Requested Status In PPP": "Widow",
        "Spouse Full Name": "Mohan Lal", "Spouse Father Name": "Hari Lal", "Date Of Death": "2026-03-12",
        "Death Certificate Number": "D-2026:06-1234"}
FAM = [{"Full Name": "Sita Devi", "Spouse Name": "Mohan Lal", "Gender": "Female"}]
CERT = {"name": "Mohan Lal", "gender": "Male", "dod": "2026-03-12", "father": "Hari Lal", "reg_no": "D-2026:06-1234",
        "unit": "MCF NIT", "reg_date": "2026-03-20"}


def make(info=None, fam=FAM, rtype="Widow"):
    raw = {"request_id": "1", "list_row": {"FamilyID": "F1", "Requested MS PPP": rtype},
           "case": {"User Info": {**INFO, "Requested Status In PPP": rtype, **(info or {})}}, "family": fam,
           "ZCRIM Remark (Ajay Singh)": {"Status": "Forwarded", "Action Date": "11-03-2026"}}
    return Request("marital", "/nonexistent", raw)


def run(req=None, cert=None, link=CRS, source="crs", status="verified", issuer=None, **kw):
    rec = Record(source, status, fields={**CERT, **(cert or {})}, error="" if status == "verified" else "page showed no certificate record")
    d = rm.analyse(req or make(), payloads=lambda r: [link] if link else [], verifiers={"crs": lambda u: rec, "ndmc": lambda u: rec, "mcd": lambda u: rec},
                   issuer=issuer or (lambda r: ("haryana", "-", "")), **kw)
    assert remark.valid(d.remark), d.remark
    return d


class Widow(unittest.TestCase):
    def test_crs_linked_by_name_and_father(self):
        d = run()
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("died 12 03 2026", d.remark)
        self.assertIn("verified through QR on official CRS portal", d.remark)
        self.assertIn("so status Widow", d.remark)
        self.assertIn("ZCRIM Ajay Singh forwarded on 11 03 2026", d.remark)

    def test_ndmc_names_applicant(self):
        d = run(link=NDMC, source="ndmc", cert={"spouse": "Sita Devi", "father": ""})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("certificate names applicant Sita Devi as wife", d.remark)

    def test_ndmc_different_spouse_rejects(self):
        d = run(link=NDMC, source="ndmc", cert={"spouse": "Geeta Rani"})
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("Different spouse", d.flags)
        self.assertIn("proof that both names are of the same person", d.remark)

    def test_ndmc_spouse_field_repeating_a_parent_is_not_a_different_spouse(self):
        d = run(link=NDMC, source="ndmc", cert={"spouse": "Gita Devi", "mother": "Gita Devi", "father": "Hari Lal"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("Spouse field repeats parent", d.flags)
        self.assertIn("father Hari Lal", d.remark)
        # a spouse that is not a parent and not the applicant is still a different spouse
        self.assertEqual(run(link=NDMC, source="ndmc", cert={"spouse": "Geeta Rani", "mother": "Gita Devi"}).recommendation, "REJECT")

    def test_mcd_text(self):
        d = run(link=MCD, source="mcd")
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("official MCD portal", d.remark)

    def test_birth_record_is_not_accepted(self):
        d = run(link=NDMC, source="ndmc", cert={"spouse": "Sita Devi", "activity": "Birth"})
        self.assertEqual((d.recommendation, d.flags), ("HOLD", ["Not a death record"]))

    def test_deceased_is_someone_else(self):
        d = run(cert={"name": "Suresh Pal"})
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("Deceased differs", d.flags)

    def test_father_in_mother_field_is_a_match(self):
        d = run(cert={"father": "Mangal Singh", "mother": "Hari Lal"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("Father in mother field", d.flags)

    def test_father_differs_but_name_and_date_of_death_match_approves_with_note(self):
        d = run(cert={"father": "Mangal Singh", "mother": "Gita Devi"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("Father differs", d.flags)
        self.assertIn("father Hari Lal on request differs from Mangal Singh on certificate", d.remark)

    def test_father_differs_without_date_match_holds(self):
        d = run(req=make({"Date Of Death": ""}), cert={"father": "Mangal Singh"})
        self.assertEqual((d.recommendation, d.flags), ("HOLD", ["Father differs"]))

    def test_name_not_in_english_is_a_note(self):
        d = run(cert={"name": "\u0930\u093e\u092e"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("Name not compared", d.flags)

    def test_one_letter_name_variant_needs_matching_date_of_death(self):
        req = make({"Spouse Full Name": "Rohan Lal"})
        self.assertEqual(run(req=req, cert={"name": "Mohan Lal"}).recommendation, "APPROVE")
        self.assertIn("Name spelling", run(req=req, cert={"name": "Mohan Lal"}).flags)
        self.assertEqual(run(req=req, cert={"name": "Mohan Lal", "dod": "2026-03-13"}).recommendation, "REJECT")

    def test_father_missing_on_certificate_approves_with_note(self):
        d = run(cert={"father": ""})
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("Father not compared", d.flags)

    def test_date_of_death_differs_holds(self):
        self.assertEqual(run(cert={"dod": "2026-03-13"}).recommendation, "HOLD")

    def test_gender_mismatch_holds(self):
        self.assertIn("Gender differs", run(cert={"gender": "Female"}).flags)

    def test_number_difference_is_only_a_flag(self):
        d = run(cert={"reg_no": "999"})
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("Number differs", d.flags)

    def test_spouse_from_ppp_row_when_request_blank(self):
        d = run(req=make({"Spouse Full Name": ""}))
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)

    def test_no_spouse_anywhere(self):
        req = make({"Spouse Full Name": ""}, fam=[{"Full Name": "Sita Devi", "Spouse Name": ""}])
        self.assertEqual(run(req=req).recommendation, "HOLD")
        req = make({"Spouse Full Name": "", "Current Status In PPP": "Unmarried"}, fam=[{"Full Name": "Sita Devi", "Spouse Name": ""}])
        d = run(req=req)
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("proof of marriage", d.remark)

    def test_widower_uses_wife(self):
        d = run(req=make({"Spouse Full Name": "Gita Devi", "Name": "Mohan Lal"}, rtype="Widower",
                         fam=[{"Full Name": "Mohan Lal", "Spouse Name": "Gita Devi"}]),
                cert={"name": "Gita Devi", "gender": "Female", "father": "Hari Lal"})
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("of wife Gita Devi", d.remark)
        self.assertIn("so status Widower", d.remark)


class Dispositions(unittest.TestCase):
    def test_site_error_holds(self):
        self.assertEqual(run(status="failed").recommendation, "HOLD")

    def test_fake_host_rejects(self):
        self.assertEqual(run(link="https://crsorgi.gov.in.evil.com/x").recommendation, "REJECT")

    def test_bare_number_holds_for_dcrim(self):
        d = run(link="1234567890")
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("DCRIM", d.remark)

    def test_unopened_government_site_approves(self):
        d = run(link="https://esewa.punjab.gov.in/verify?x=1")
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("not opened", d.remark)

    def test_no_qr_by_issuer(self):
        self.assertEqual(run(link=None).recommendation, "REJECT")
        self.assertIn("visit the office of ADC", run(link=None).remark)
        d = run(link=None, issuer=lambda r: ("uttar pradesh", "-", ""))
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("issued by uttar pradesh", d.remark)

    def test_unmarried_waits_for_officer(self):
        self.assertEqual(run(req=make(rtype="Unmarried")).recommendation, "HOLD")


ULB = "http://edisha.gov.in/Default_VerifyCertificate.aspx?tid=1&cid=2&aid=5"
MARRIAGE = {"marriage_date": "2024-03-07", "bride_name": "Sita Devi", "bride_dob": "2002-06-05", "bride_father": "Ram Lal",
            "bride_mother": "Gita", "groom_name": "Mohan Lal", "groom_dob": "1999-05-01", "groom_father": "Hari Lal",
            "groom_mother": "Rani", "reg_no": "59", "reg_date": "2024-03-27", "issued_by": "Sub Registrar Ballabgarh"}
MINFO = {"Name": "Sita Devi", "Father Name": "Ram Lal", "Mother Name": "Gita", "Current Status In PPP": "Unmarried",
         "Spouse Full Name": "Mohan Lal", "Spouse Father Name": "NA", "Is Marriage Registered In Haryana": "Yes"}
MFAM = [{"Full Name": "Sita Devi", "Spouse Name": "", "Gender": "Female", "Date of Birth": "05/06/2002", "Relation With HOF": "WIFE"}]


def married(info=None, cert=None, link=ULB, fam=MFAM):
    from analyser.rules_marriage import SOURCE_NAMES  # noqa: F401
    req = make({**MINFO, **(info or {})}, fam=fam, rtype="Married")
    rec = Record("edisha", "verified", fields={**MARRIAGE, **(cert or {})})
    d = rm.analyse(req, payloads=lambda r: [link] if link else [], marriage_verifier=lambda u: rec,
                   issuer=lambda r: ("haryana", "-", ""))
    assert remark.valid(d.remark), d.remark
    return d


class Married(unittest.TestCase):
    def test_adult_couple_approves_with_status_wording(self):
        d = married()
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("so status Married", d.remark)
        self.assertIn("bride aged 21 years 9 months", d.remark)
        self.assertNotIn("Confirm on portal", d.flags)

    def test_underage_bride_rejects(self):
        d = married(cert={"bride_dob": "2007-01-01"}, fam=[{**MFAM[0], "Date of Birth": "01/01/2007"}])
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("Underage", d.flags)

    def test_placeholder_spouse_father_is_ignored_but_a_real_one_is_compared(self):
        self.assertEqual(married().recommendation, "APPROVE")
        self.assertEqual(married({"Spouse Father Name": "Hari Lal"}).recommendation, "APPROVE")
        self.assertEqual(married({"Spouse Father Name": "Mangal Singh"}).recommendation, "HOLD")

    def test_applicant_not_on_certificate_rejects(self):
        self.assertEqual(married({"Name": "Geeta Kumari"}, fam=[{**MFAM[0], "Full Name": "Geeta Kumari"}]).recommendation, "REJECT")

    def test_unopened_government_site(self):
        d = married(link="https://ucc.uk.gov.in/verify?x=1")
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("not opened", d.remark)

    def test_no_qr_haryana_rejects(self):
        self.assertEqual(married(link=None).recommendation, "REJECT")


if __name__ == "__main__":
    unittest.main()
