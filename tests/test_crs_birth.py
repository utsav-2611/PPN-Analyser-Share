import unittest

from analyser.verify import crs_birth

PAGE = """Home
Registration Number\tB-2001:06-123
NAME\tSita Devi
GENDER\tFemale / \u092e\u0939\u093f\u0932\u093e
DOB\t23-03-2001
Name Of Mother\tKamla Devi
Name Of Father\tRam Lal
Place of Birth\tCivil Hospital, Palwal
Registration Date\t30-03-2001
Registration Unit Name\tCivil Hospital
Registration Unit Code\t4
Last Updated: 30-01-2024"""


class Parse(unittest.TestCase):
    def test_fields(self):
        f = crs_birth.parse(PAGE)
        self.assertEqual(f["dob"], "2001-03-23")
        self.assertEqual(f["reg_date"], "2001-03-30")
        self.assertEqual((f["name"], f["father"], f["mother"]), ("Sita Devi", "Ram Lal", "Kamla Devi"))
        self.assertEqual(f["reg_no"], "B-2001:06-123")
        self.assertEqual(f["unit"], "Civil Hospital")

    def test_other_date_styles(self):
        f = crs_birth.parse("Registration Number\tB1\nDOB\t23-Mar-2001\nRegistration Date\t30 March 2001")
        self.assertEqual((f["dob"], f["reg_date"]), ("2001-03-23", "2001-03-30"))

    def test_page_without_record(self):
        self.assertEqual(crs_birth.parse("Home\nAbout CRS"), {})


if __name__ == "__main__":
    unittest.main()
