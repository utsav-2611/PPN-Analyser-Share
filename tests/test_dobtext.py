import unittest
from datetime import date

from analyser import dobtext as d


class Dates(unittest.TestCase):
    def test_numeric_and_names(self):
        t = "Date of Birth 23/03/2005 and 4 Jan 1999, also March 7th, 2001 and १२-०३-२००५"
        self.assertEqual(d.dates_in(t), {date(2005, 3, 23), date(1999, 1, 4), date(2001, 3, 7), date(2005, 3, 12)})

    def test_words(self):
        self.assertEqual(d.dates_in("(in words) Twenty Third June Two Thousand Five"), {date(2005, 6, 23)})
        self.assertEqual(d.dates_in("Thirty First December Two Thousand and Nine"), {date(2009, 12, 31)})
        self.assertEqual(d.dates_in("Fifth March Nineteen Ninety Eight"), {date(1998, 3, 5)})
        self.assertEqual(d.dates_in("First of May One Thousand Nine Hundred Ninety Two"), {date(1992, 5, 1)})
        self.assertEqual(d.dates_in("Twenty Eighth February Two Thousand"), {date(2000, 2, 28)})

    def test_bad_dates_ignored(self):
        self.assertEqual(d.dates_in("31/02/2005 and 45/01/2000"), set())

    def test_find_dob(self):
        t = "Birth: 23/03/2005"
        self.assertEqual(d.find_dob(t, date(2005, 3, 23)), "exact")
        self.assertEqual(d.find_dob(t, date(2005, 3, 28)), "one digit off")
        self.assertIsNone(d.find_dob(t, date(2004, 1, 1)))
        self.assertIsNone(d.find_dob(t, None))

    def test_age_split_over_lines(self):
        self.assertEqual(d.ages_as_on("Age as on 1.1.2019\n: 35\nYears"), [(date(2019, 1, 1), 35)])
        self.assertEqual(d.ages_as_on("Age as on 01.01.2019 : 35 Years"), [(date(2019, 1, 1), 35)])

    def test_split_year_and_word_day(self):
        self.assertEqual(d.dates_in("Date of Birth 12 Feb 20 05"), {date(2005, 2, 12)})
        self.assertEqual(d.dates_in("Date of Birth Twelfth Feb 2005"), {date(2005, 2, 12)})
        self.assertEqual(d.dates_in("Twenty Third Feb 20 05"), {date(2005, 2, 23)})

    def test_dob_context_ignores_footnote_and_age_lines(self):
        t = "Age as on 1.1.2019\nDate of Birth in the card is as per roll 2019\nDate of Birth: 23/03/2005"
        self.assertEqual(d.dob_context(t), ({date(2005, 3, 23)}, {2005}))
        self.assertEqual(d.dob_context("Date of Birth\n2005", same_line=True), (set(), set()))
        self.assertEqual(d.dob_context("Date of Birth\n2005"), (set(), {2005}))

    def test_age_far_from_its_date(self):
        t = "Age as on 1.1.2019\nSex: Male\nName: x\n35\nYears"
        self.assertEqual(d.ages_as_on(t), [(date(2019, 1, 1), 35)])

    def test_loose_forms(self):
        from datetime import date
        t = date(2004, 3, 8)
        self.assertEqual(d.find_dob("Date of Birth 08/03/04", t), "exact")
        self.assertEqual(d.find_dob("born 8-3-04", t), "exact")
        self.assertEqual(d.find_dob("Date of Birth 09/03/04", t), None)
        self.assertEqual(d.find_dob("8\nMarch\n2004", t), "exact")
        self.assertEqual(d.find_dob("8\nDecember\n2004", t), None)
        self.assertEqual(d.find_dob("08/03/05", t), None)

    def test_hindi_months_and_digit_slips(self):
        from datetime import date
        t = date(2004, 1, 5)
        self.assertEqual(d.find_dob("जन्म तिथि 5 जनवरी 2004", t), "exact")
        self.assertEqual(d.find_dob("जन्म तिथि ५ जनवरी २००४", t), "exact")
        self.assertEqual(d.find_dob("DATE OF BIRTH : O5/Ol/2004", t), "exact")
        self.assertEqual(d.find_dob("DATE OF BIRTH : 26/Ol/2004", t), None)
        self.assertEqual(d.find_dob("Some Of Lot", t), None)
        self.assertEqual(d.fix_digit_slips("Ol Oct SOB"), "Ol Oct SOB")

    def test_plain_age(self):
        self.assertEqual(d.plain_ages("Date of Birth / Age : 35"), [35])
        self.assertEqual(d.plain_ages("Date of Birth Age; 41;"), [41])
        self.assertEqual(d.plain_ages("Date of Birth & Age; 52;"), [52])
        self.assertEqual(d.plain_ages("Date of Birth and Age : 28"), [28])
        self.assertEqual(d.plain_ages("nothing"), [])

    def test_age_as_on(self):
        self.assertEqual(d.ages_as_on("Age as on 1.1.2019 : 35 Years"), [(date(2019, 1, 1), 35)])
        self.assertEqual(d.ages_as_on("nothing"), [])


if __name__ == "__main__":
    unittest.main()
