import unittest
from datetime import date

from analyser import match as m


class NameMatch(unittest.TestCase):
    def test_exact_ignores_case_titles_order(self):
        self.assertEqual(m.name_match("SMT. Sita  Devi", "sita devi"), "exact")
        self.assertEqual(m.name_match("Late Ram Kumar", "Kumar Ram"), "exact")

    def test_spelling_variants(self):
        self.assertEqual(m.name_match("Mohammed Rafiq", "Mohamad Rafik"), "close")
        self.assertEqual(m.name_match("Rajinder Singh", "Rajender Singh"), "close")

    def test_surname_one_letter_variant(self):
        self.assertEqual(m.name_match("Kavita Yadav", "Kavita Yadev"), "close")
        self.assertEqual(m.name_match("Mohammed Rafiq Yadav", "Mohamad Rafik Yadev"), "close")
        self.assertEqual(m.name_match("Sunita Sharma", "Sunita Verma"), "none")
        self.assertEqual(m.name_match("Suresh Kumari", "Ramesh Kumari"), "none")

    def test_one_letter_variant_is_a_separate_weaker_test(self):
        self.assertTrue(m.one_letter_variant("Mohan Lal", "Rohan Lal"))
        self.assertFalse(m.one_letter_variant("Sunita Rani", "Sunita Rani"))  # no odd word: name_match already handles it
        self.assertFalse(m.one_letter_variant("Mohan Lal", "Rohan Pal"))
        self.assertFalse(m.one_letter_variant("Mohan", "Mohan Lal"))
        self.assertEqual(m.name_match("Mohan Lal", "Rohan Lal"), "none")  # name_match itself stays strict

    def test_partial_missing_surname(self):
        self.assertEqual(m.name_match("Ram Kumar", "Ram Kumar Sharma"), "partial")
        self.assertEqual(m.name_match("R K Sharma", "Ram Kumar Sharma"), "partial")

    def test_different_people(self):
        self.assertEqual(m.name_match("Saleem", "Sakim Khan"), "none")
        self.assertEqual(m.name_match("Sita Devi", "Geeta Devi"), "none")

    def test_missing(self):
        self.assertEqual(m.name_match("", "Ram"), "missing")

    def test_acceptable(self):
        self.assertTrue(m.acceptable("Ram Kumar", "Ram Kumar Sharma"))
        self.assertFalse(m.acceptable("Ram Kumar", "Ram Kumar Sharma", allow_partial=False))


class Dates(unittest.TestCase):
    def test_parse(self):
        d = date(2025, 10, 25)
        for s in ("25/10/2025", "25-10-2025", "25.10.2025", "25 10 2025", "2025-10-25"):
            self.assertEqual(m.parse_date(s), d)
        self.assertIsNone(m.parse_date("31/02/2025"))
        self.assertIsNone(m.parse_date("garbage"))

    def test_age_exact(self):
        self.assertEqual(m.age_on(date(2006, 3, 8), date(2024, 3, 7)), (17, 11))
        self.assertEqual(m.age_on(date(2006, 3, 7), date(2024, 3, 7)), (18, 0))
        self.assertEqual(m.age_on(date(2003, 3, 7), date(2024, 3, 6)), (20, 11))

    def test_months_and_birthdays(self):
        self.assertEqual(m.add_months(date(2023, 11, 10), -9), date(2023, 2, 10))
        self.assertEqual(m.add_months(date(2024, 5, 31), -3), date(2024, 2, 29))
        self.assertEqual(m.birthday(date(2005, 10, 6), 18), date(2023, 10, 6))
        self.assertEqual(m.birthday(date(2004, 2, 29), 18), date(2022, 2, 28))

    def test_fmt(self):
        self.assertEqual(m.fmt_date(date(2025, 3, 7)), "07 03 2025")


if __name__ == "__main__":
    unittest.main()
