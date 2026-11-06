import unittest
from datetime import date

from analyser import remark, rules_dob as rd
from analyser.load import Request

INFO = {"Name": "Sita Devi", "DOB In PPP": "01-01-2000", "Requested DOB": "23-03-2001", "Uploaded Document": "Matric Mark Sheet/Certificate",
        "Document Number": "NA"}


def make(info=None):
    raw = {"request_id": "1", "list_row": {"FamilyID": "F1"}, "case": {"User Info": {**INFO, **(info or {})}},
           "ZCRIM Remark (Ajay Singh)": {"Status": "Forwarded", "Action Date": "11-03-2026"}}
    return Request("dob", "/nonexistent", raw)


def run(ev, info=None):
    d = rd.analyse(make(info), evidence=ev)
    assert remark.valid(d.remark), d.remark
    return d


class ClassifySecondary(unittest.TestCase):
    def test_secondary_examination_is_a_board_certificate(self):
        label = "School Leaving Certificate/SSC Certificate"
        self.assertEqual(rd.classify_text("SECONDARY SCHOOL EXAMINATION (March 2019)", label), rd.BOARD)
        self.assertEqual(rd.classify_text("Certificate of Secondary Examination", label), rd.BOARD)
        self.assertEqual(rd.classify_text("स्थानान्तरण प्रमाण पत्र", label), rd.SLC)
        self.assertEqual(rd.classify_text("some other paper", label), rd.SCHOOL)


class FixedDobDocuments(unittest.TestCase):
    def test_board_certificate_with_dob_approves(self):
        d = run(rd.Evidence(doc_class=rd.BOARD, dob_found="exact"))
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("shows DOB 23 03 2001 same as requested DOB", d.remark)
        self.assertIn("ZCRIM Ajay Singh forwarded on 11 03 2026", d.remark)

    def test_no_change_still_needs_the_document(self):
        d = run(rd.Evidence(doc_class=rd.PASSPORT, dob_found="exact"), {"Requested DOB": "01-01-2000"})
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("so no change", d.remark)

    def test_dob_not_found_holds(self):
        d = run(rd.Evidence(doc_class=rd.BOARD))
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("not found in Board certificate text", d.remark)

    def test_old_ppp_date_is_mentioned(self):
        d = run(rd.Evidence(doc_class=rd.BOARD, ppp_shown=True))
        self.assertIn("old PPP DOB is written there instead", d.remark)

    def test_one_digit_off_holds(self):
        self.assertEqual(run(rd.Evidence(doc_class=rd.BOARD, dob_found="one digit off")).recommendation, "HOLD")
        ev = rd.Evidence(doc_class=rd.BOARD, dob_dates={date(2001, 3, 28)})
        self.assertEqual(run(ev).recommendation, "HOLD")

    def test_full_date_readable_must_match(self):
        ev = rd.Evidence(doc_class=rd.BOARD, dob_dates={date(2002, 5, 9)}, dob_years={2002})
        d = run(ev)
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("shows DOB 09 05 2002 which does not match requested DOB 23 03 2001", d.remark)

    def test_several_dates_hold(self):
        ev = rd.Evidence(doc_class=rd.BOARD, dob_dates={date(2002, 5, 9), date(2003, 1, 1)})
        self.assertEqual(run(ev).recommendation, "HOLD")

    def test_year_only_matching_approves(self):
        d = run(rd.Evidence(doc_class=rd.BOARD, dob_years={2001}))
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("year 2001 is readable and same as requested", d.remark)

    def test_year_only_differing_rejects(self):
        d = run(rd.Evidence(doc_class=rd.BOARD, dob_years={2003}))
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("shows year 2003", d.remark)

    def test_unreadable_holds(self):
        self.assertEqual(run(rd.Evidence(doc_class=rd.BOARD, readable=False)).recommendation, "HOLD")

    def test_no_document_rejects(self):
        d = run(rd.Evidence(doc_class="none"))
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("No document uploaded", d.remark)

    def test_discharge_certificate(self):
        ev = rd.Evidence(doc_class=rd.GOVT_ID, discharge_dob=date(2001, 3, 23))
        self.assertEqual(run(ev).recommendation, "APPROVE")
        ev = rd.Evidence(doc_class=rd.GOVT_ID, discharge_dob=date(2001, 3, 24))
        self.assertEqual(run(ev).recommendation, "HOLD")


class SchoolLeavingCertificate(unittest.TestCase):
    def slc(self, **kw):
        return rd.Evidence(doc_class=rd.SLC, register_copy=True, school_state="haryana", dob_found="exact", **kw)

    def test_haryana_school_accepted_for_any_change(self):
        d = run(self.slc(), {"Requested DOB": "02-01-2008"})
        self.assertEqual(d.recommendation, "APPROVE", d.remark)

    def test_outside_haryana_over_two_years_rejects(self):
        ev = self.slc()
        ev.school_state = "other"
        d = run(ev, {"Requested DOB": "02-01-2003"})
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("outside Haryana is not accepted for a change of more than 2 years", d.remark)
        d = run(ev, {"Requested DOB": "31-12-1997"})
        self.assertEqual(d.recommendation, "REJECT")

    def test_outside_haryana_within_two_years_is_checked_like_board(self):
        ev = self.slc()
        ev.school_state = "other"
        self.assertEqual(run(ev, {"Requested DOB": "01-01-2002"}).recommendation, "APPROVE")

    def test_state_unreadable_with_big_change_holds(self):
        ev = self.slc()
        ev.school_state = "unknown"
        self.assertEqual(run(ev, {"Requested DOB": "02-01-2003"}).recommendation, "HOLD")
        self.assertEqual(run(ev, {"Requested DOB": "01-01-2001"}).recommendation, "APPROVE")

    def test_register_copy_missing_rejects(self):
        ev = self.slc()
        ev.register_copy = False
        d = run(ev)
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("entry exit register", d.remark)

    def test_unclear_school_document_with_big_change_holds(self):
        d = run(rd.Evidence(doc_class=rd.SCHOOL, dob_found="exact"), {"Requested DOB": "01-01-2005"})
        self.assertEqual(d.recommendation, "HOLD")

    def test_board_certificate_may_change_by_more(self):
        d = run(rd.Evidence(doc_class=rd.BOARD, dob_found="exact"), {"Requested DOB": "01-01-2005"})
        self.assertEqual(d.recommendation, "APPROVE")


class VoterId(unittest.TestCase):
    ROW = [{"epic": "ABC1234567", "deleted": 0}]
    INFO = {"Uploaded Document": "Voter ID", "Document Number": "ABC1234567"}

    def test_dob_on_card(self):
        d = run(rd.Evidence(doc_class=rd.VOTER, epic_rows=self.ROW, dob_found="exact"), self.INFO)
        self.assertEqual(d.recommendation, "APPROVE", d.analysis)
        self.assertIn("EPIC verified in electoral roll", d.remark)

    def test_year_only_on_card(self):
        d = run(rd.Evidence(doc_class=rd.VOTER, epic_rows=self.ROW, dob_years={2001}), self.INFO)
        self.assertEqual(d.recommendation, "APPROVE")

    def test_age_range_fits(self):
        ev = rd.Evidence(doc_class=rd.VOTER, epic_rows=self.ROW, ages=[(date(2019, 1, 1), 18)])
        d = run(ev, {**self.INFO, "Requested DOB": "15-06-2000"})
        self.assertEqual(d.recommendation, "APPROVE", d.remark)

    def test_age_range_outside_rejects(self):
        ev = rd.Evidence(doc_class=rd.VOTER, epic_rows=self.ROW, ages=[(date(2019, 1, 1), 18)])
        d = run(ev, {**self.INFO, "Requested DOB": "15-06-1995"})
        self.assertEqual(d.recommendation, "REJECT")

    def test_epic_not_in_roll_rejects(self):
        d = run(rd.Evidence(doc_class=rd.VOTER, epic_rows=[], dob_found="exact"), self.INFO)
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("not found in the electoral roll", d.remark)

    def test_issued_after_2019_rejects(self):
        d = run(rd.Evidence(doc_class=rd.VOTER, epic_rows=self.ROW, dob_found="exact", issue_year=2021), self.INFO)
        self.assertEqual(d.recommendation, "REJECT")

    def test_nothing_readable_holds(self):
        d = run(rd.Evidence(doc_class=rd.VOTER, epic_rows=self.ROW, readable=False), self.INFO)
        self.assertEqual(d.recommendation, "HOLD")

    def test_no_dob_and_no_age_on_card_uses_roll_age(self):
        roll = [{"epic": "ABC1234567", "age": 18, "age_as_on": "01-01-2019", "deleted": 0}]
        ev = rd.Evidence(doc_class=rd.VOTER, epic_rows=roll)
        d = run(ev, {**self.INFO, "Requested DOB": "15-06-2000"})
        self.assertEqual(d.recommendation, "APPROVE", d.remark)
        self.assertIn("age 18 as on 01 01 2019", d.remark)
        self.assertEqual(run(ev, {**self.INFO, "Requested DOB": "15-06-1990"}).recommendation, "REJECT")

    def test_a_different_full_date_on_card_still_rejects(self):
        roll = [{"epic": "ABC1234567", "age": 18, "age_as_on": "01-01-2019", "deleted": 0}]
        ev = rd.Evidence(doc_class=rd.VOTER, epic_rows=roll, dob_dates={date(1999, 1, 1)})
        self.assertEqual(run(ev, {**self.INFO, "Requested DOB": "15-06-2000"}).recommendation, "REJECT")

    def test_epic_not_typed_or_read_holds(self):
        self.assertEqual(run(rd.Evidence(doc_class=rd.VOTER), self.INFO).recommendation, "HOLD")

    def test_undated_card_age_is_ignored_roll_decides(self):
        roll = [{"epic": "ABC1234567", "age": 18, "age_as_on": "01-01-2019", "deleted": 0}]
        ev = rd.Evidence(doc_class=rd.VOTER, epic_rows=roll, plain_age=40)   # the undated card age is ignored
        self.assertEqual(run(ev, {**self.INFO, "Requested DOB": "15-06-2000"}).recommendation, "APPROVE")
        self.assertEqual(run(ev, {**self.INFO, "Requested DOB": "15-06-1990"}).recommendation, "REJECT")   # decided from the roll age
        ev = rd.Evidence(doc_class=rd.VOTER, epic_rows=[{"epic": "X", "age": None, "age_as_on": None}], plain_age=18)
        self.assertEqual(run(ev, self.INFO).recommendation, "HOLD")


class ElectoralRollCertificate(unittest.TestCase):
    INFO = {"Uploaded Document": "Voter ID", "Document Number": "ABC1234567", "Requested DOB": "15-06-2000"}
    ROLL = [{"epic": "ABC1234567", "age": 18, "age_as_on": "01-01-2019", "deleted": 0}]

    def test_epic_not_in_roll_rejects(self):
        d = run(rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=[], diary="123 of 05 06 2026"), self.INFO)
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("diary no 123 of 05 06 2026", d.remark)
        self.assertIn("Roll certificate EPIC not in roll", d.flags)

    def test_epic_not_typed_or_read_holds(self):
        self.assertEqual(run(rd.Evidence(doc_class=rd.ROLL_CERT), self.INFO).recommendation, "HOLD")

    def test_certificate_agrees_with_roll_approves(self):
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, ages=[(date(2019, 1, 1), 18)])
        d = run(ev, self.INFO)
        self.assertEqual(d.recommendation, "APPROVE", d.remark)

    def test_certificate_differs_from_roll_rejects(self):
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, ages=[(date(2019, 1, 1), 25)])
        self.assertEqual(run(ev, {**self.INFO, "Requested DOB": "15-06-1993"}).recommendation, "REJECT")

    def test_certificate_dob_checked_against_roll_age(self):
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, dob_dates={date(2000, 6, 15)})
        self.assertEqual(run(ev, self.INFO).recommendation, "APPROVE")
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, dob_dates={date(1990, 6, 15)})
        self.assertEqual(run(ev, {**self.INFO, "Requested DOB": "15-06-1990"}).recommendation, "REJECT")

    def test_nothing_readable_uses_roll_age(self):
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL)
        self.assertEqual(run(ev, self.INFO).recommendation, "APPROVE")
        self.assertEqual(run(ev, {**self.INFO, "Requested DOB": "15-06-1990"}).recommendation, "REJECT")
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=[{"epic": "X", "age": None, "age_as_on": None}])
        self.assertEqual(run(ev, self.INFO).recommendation, "HOLD")

    def test_plain_age_agrees_with_roll(self):
        # roll age 18 on 01 01 2019; a certificate written years later may show a higher age
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, plain_age=18)
        self.assertEqual(run(ev, self.INFO).recommendation, "APPROVE")
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, plain_age=25)
        self.assertEqual(run(ev, self.INFO).recommendation, "APPROVE")
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, plain_age=40)
        self.assertEqual(run(ev, self.INFO).recommendation, "REJECT")
        ev = rd.Evidence(doc_class=rd.ROLL_CERT, epic_rows=self.ROLL, plain_age=10)
        self.assertEqual(run(ev, self.INFO).recommendation, "REJECT")


class BirthCertificate(unittest.TestCase):
    INFO = {"Uploaded Document": "Birth Certificate", "Name": "Sita Devi", "Father Name": "Ram Lal", "Mother Name": "Kamla Devi"}

    def record(self, **kw):
        base = {"dob": date(2001, 3, 23), "name": "Sita Devi", "father": "Ram Lal", "mother": "Kamla Devi", "reg_no": "B-2001:06-123"}
        return rd.Evidence(doc_class=rd.BIRTH, qr_kind="official", qr_host="dc.crsorgi.gov.in", birth_record={**base, **kw})

    def test_record_matches_names_and_parents(self):
        d = run(self.record(), self.INFO)
        self.assertEqual(d.recommendation, "APPROVE", d.remark)
        self.assertIn("Reg No B 2001 06 123 verified through QR on official CRS portal", d.remark)

    def test_mother_differs_is_a_note(self):
        d = run(self.record(mother="Radha"), self.INFO)
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("mother name Radha differs", d.remark)

    def test_name_differs_with_parents_matching_is_a_note(self):
        d = run(self.record(name="Baby"), self.INFO)
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertIn("name Baby differs", d.remark)

    def test_father_differs_holds(self):
        self.assertEqual(run(self.record(father="Mohan"), self.INFO).recommendation, "HOLD")

    def test_both_parents_differ(self):
        self.assertEqual(run(self.record(father="Mohan", mother="Radha"), self.INFO).recommendation, "HOLD")
        self.assertEqual(run(self.record(name="Geeta", father="Mohan", mother="Radha"), self.INFO).recommendation, "REJECT")

    def test_blank_parents_in_record_do_not_block(self):
        self.assertEqual(run(self.record(father="", mother=""), self.INFO).recommendation, "APPROVE")

    def test_gather_helper_reads_a_verified_record(self):
        from analyser.verify.base import Record
        rec = Record("crs birth", "verified", fields={"dob": "2001-03-23", "name": "X", "reg_no": "B1"})
        out = rd._birth_record_of("see https://dc.crsorgi.gov.in/crs/verifyCertificate?id=QUJD", verifier=lambda u: rec)
        self.assertEqual(out["dob"], date(2001, 3, 23))
        bad = Record("crs birth", "na", error="x")
        self.assertIsNone(rd._birth_record_of("https://dc.crsorgi.gov.in/x", verifier=lambda u: bad))

    def test_verified_record_matches(self):
        ev = rd.Evidence(doc_class=rd.BIRTH, qr_kind="official", qr_host="dc.crsorgi.gov.in", qr_opened=True,
                         birth_record={"dob": date(2001, 3, 23), "name": "x"})
        d = run(ev, self.INFO)
        self.assertEqual(d.recommendation, "APPROVE")
        self.assertEqual(d.verification_status, "verified")

    def test_verified_record_differs_rejects(self):
        ev = rd.Evidence(doc_class=rd.BIRTH, qr_kind="official", qr_opened=True, birth_record={"dob": date(2001, 3, 24), "name": "x"})
        self.assertEqual(run(ev, self.INFO).recommendation, "REJECT")

    def test_fake_qr_rejects(self):
        ev = rd.Evidence(doc_class=rd.BIRTH, qr_kind="fake_host", qr_host="dc.crsorgi.com.cer-verify.com")
        d = run(ev, self.INFO)
        self.assertEqual(d.recommendation, "REJECT")
        self.assertIn("non official site", d.remark)

    def test_no_qr_haryana_rejects_other_holds(self):
        self.assertEqual(run(rd.Evidence(doc_class=rd.BIRTH, issuer="haryana"), self.INFO).recommendation, "REJECT")
        self.assertEqual(run(rd.Evidence(doc_class=rd.BIRTH, issuer="uttar pradesh"), self.INFO).recommendation, "HOLD")

    def test_no_qr_but_dob_matches_approves_from_2000(self):
        ev = rd.Evidence(doc_class=rd.BIRTH, issuer="haryana", dob_found="exact")
        d = run(ev, self.INFO | {"Requested DOB": "31-12-1999"})
        self.assertEqual(d.recommendation, "REJECT")          # before 2000: still the QR rule
        d = run(ev, self.INFO | {"Requested DOB": "01-01-2000"})
        self.assertEqual(d.recommendation, "APPROVE", d.remark)
        self.assertEqual(run(rd.Evidence(doc_class=rd.BIRTH, issuer="uttar pradesh", dob_found="exact"), self.INFO | {"DOB In PPP": "23-03-2001"}).recommendation, "APPROVE")
        self.assertEqual(run(rd.Evidence(doc_class=rd.BIRTH, issuer="haryana"), self.INFO).recommendation, "REJECT")  # DOB not confirmed

    def test_no_qr_dob_changed_from_ppp(self):
        changed = self.INFO | {"Requested DOB": "01-01-2001", "DOB In PPP": "01-01-2000"}
        ev = rd.Evidence(doc_class=rd.BIRTH, issuer="haryana", dob_found="exact")
        self.assertEqual(run(ev, changed).recommendation, "REJECT")   # Haryana certificate: QR readability is needed
        other = rd.Evidence(doc_class=rd.BIRTH, issuer="uttar pradesh", dob_found="exact")
        d = run(other, changed)
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("PPP DOB changed", d.flags[0])
        self.assertEqual(run(ev, self.INFO | {"Requested DOB": "01-01-2001", "DOB In PPP": "01-01-2001"}).recommendation, "APPROVE")

    def test_crs_portal_not_read_holds(self):
        ev = rd.Evidence(doc_class=rd.BIRTH, qr_kind="official", qr_host="dc.crsorgi.gov.in", dob_found="exact")
        d = run(ev, self.INFO)
        self.assertEqual(d.recommendation, "HOLD")
        self.assertIn("record could not be read", d.remark)

    def test_government_site_not_opened(self):
        ev = rd.Evidence(doc_class=rd.BIRTH, qr_kind="official", qr_host="x.gov.in", dob_found="exact")
        self.assertEqual(run(ev, self.INFO).recommendation, "APPROVE")
        ev = rd.Evidence(doc_class=rd.BIRTH, qr_kind="official", qr_host="x.gov.in")
        self.assertEqual(run(ev, self.INFO).recommendation, "HOLD")

    def test_plain_text_qr_holds(self):
        self.assertEqual(run(rd.Evidence(doc_class=rd.BIRTH, qr_kind="plain_text"), self.INFO).recommendation, "HOLD")


class Retry(unittest.TestCase):
    NEW = date(2001, 3, 23)

    def test_first_pass_found_never_calls_variants(self):
        def boom():
            raise AssertionError("variants must not be read")
            yield
        found, text = rd._retry_with_variants("Date of Birth 23/03/2001", self.NEW, boom())
        self.assertEqual(found, "exact")

    def test_second_variant_finds_it(self):
        seen = []

        def variants():
            for t in ("nothing here", "DOB 23-03-2001", "never reached"):
                seen.append(t)
                yield t
        found, text = rd._retry_with_variants("blurry", self.NEW, variants())
        self.assertEqual(found, "exact")
        self.assertEqual(seen, ["nothing here", "DOB 23-03-2001"])
        self.assertIn("DOB 23-03-2001", text)

    def test_nothing_found_keeps_the_first_pass_result(self):
        found, text = rd._retry_with_variants("Birth 28/03/2001", self.NEW, iter(["x", "y"]))
        self.assertEqual(found, "one digit off")
        self.assertEqual(text, "Birth 28/03/2001")


class SchoolState(unittest.TestCase):
    def test_state(self):
        self.assertEqual(rd._school_state("Govt Sr Sec School Hodal Distt Palwal"), "haryana")
        self.assertEqual(rd._school_state("राजकीय विद्यालय पलवल"), "haryana")
        self.assertEqual(rd._school_state("Board of Secondary Education Rajasthan Ajmer"), "other")
        self.assertEqual(rd._school_state("school leaving certificate"), "unknown")
        self.assertEqual(rd._school_state("Jindal Public School Jaipur Rajasthan"), "other")


class Classify(unittest.TestCase):
    def test_label_decides_simple_ones(self):
        self.assertEqual(rd.classify_text("", "Passport"), rd.PASSPORT)
        self.assertEqual(rd.classify_text("", "Birth Certificate"), rd.BIRTH)
        self.assertEqual(rd.classify_text("", "Discharge Certificate issued by the Armed Forces"), rd.GOVT_ID)

    def test_text_decides_school_and_voter(self):
        self.assertEqual(rd.classify_text("Board of School Education Haryana Roll No 1 Marks", "School Leaving Certificate/SSC Certificate"), rd.BOARD)
        self.assertEqual(rd.classify_text("School Leaving Certificate admission no 5", "School Leaving Certificate/SSC Certificate"), rd.SLC)
        self.assertEqual(rd.classify_text("ELECTOR'S NAME ELECTION COMMISSION OF INDIA", "Voter ID"), rd.VOTER)
        self.assertEqual(rd.classify_text("Electoral Roll Certificate diary no 5", "Voter ID"), rd.ROLL_CERT)
        self.assertEqual(rd.classify_text("blurry", "School Leaving Certificate/SSC Certificate"), rd.SCHOOL)


if __name__ == "__main__":
    unittest.main()


class FindEpic(unittest.TestCase):
    def test_reads_both_styles(self):
        from analyser import electors
        self.assertEqual(electors.find_epic("EPIC No : ABC 1234567 Name"), "ABC1234567")
        self.assertEqual(electors.find_epic("no HR/12/123/456789 here"), "HR/12/123/456789")
        self.assertEqual(electors.find_epic("nothing"), "")
