import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from analyser import electors, match


class AgeRange(unittest.TestCase):
    def test_range_is_one_year_before_the_date(self):
        lo, hi = match.dob_range_for_age(30, date(2019, 1, 1))
        self.assertEqual((lo, hi), (date(1988, 1, 2), date(1989, 1, 1)))

    def test_fits(self):
        self.assertTrue(match.dob_fits_age(date(1988, 6, 15), 30, date(2019, 1, 1)))
        self.assertTrue(match.dob_fits_age(date(1989, 1, 1), 30, date(2019, 1, 1)))
        self.assertFalse(match.dob_fits_age(date(1988, 1, 1), 30, date(2019, 1, 1)))
        self.assertFalse(match.dob_fits_age(date(1990, 1, 1), 30, date(2019, 1, 1)))

    def test_leap_day(self):
        lo, hi = match.dob_range_for_age(20, date(2020, 2, 29))
        self.assertEqual(hi, date(2000, 2, 29))
        self.assertEqual(lo, date(1999, 3, 1))


class Lookup(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = Path(self.dir.name) / "electors.db"
        con = sqlite3.connect(self.db)
        con.execute("create table electors (ac_no, ac_name, part_no, serial_no, epic, name, relation_type, "
                    "relation_name, house_no, age, gender, age_as_on, deleted)")
        con.executemany("insert into electors values (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            (1, "X", 5, 1, "ABC1234567", "n1", "father", "f1", "1", 40, "M", "1-1-2019", 0),
            (1, "X", 5, 2, "HR/12/123/456789", "n2", "husband", "h2", "2", 33, "F", "1-1-2019", 0),
        ])
        con.commit()
        con.close()

    def tearDown(self):
        self.dir.cleanup()

    def test_normalize(self):
        self.assertEqual(electors.normalize_epic(" hr/12/123/456789 "), "HR12123456789")

    def test_plain_and_slashed(self):
        self.assertEqual(electors.lookup("abc1234567", self.db)[0]["serial_no"], 1)
        self.assertEqual(electors.lookup("HR12123456789", self.db)[0]["serial_no"], 2)
        self.assertEqual(electors.lookup("HR/12/123/456789", self.db)[0]["serial_no"], 2)

    def test_variants(self):
        self.assertEqual(electors.variants("HR/12/123/0456789"), ["HR121230456789", "HR12123456789"])
        self.assertEqual(electors.variants("HR/12/123/456789"), ["HR12123456789", "HR121230456789"])
        self.assertEqual(electors.variants("ABC1234567"), ["ABC1234567", "ABC01234567"])
        self.assertEqual(electors.variants(""), [])

    def test_zero_variants_found(self):
        self.assertEqual(electors.lookup("HR/12/123/0456789", self.db)[0]["serial_no"], 2)
        self.assertEqual(electors.lookup("HR/12/123/56789", self.db), [])
        self.assertEqual(electors.lookup("ABC01234567", self.db)[0]["serial_no"], 1)
        self.assertEqual(electors.lookup("ABC1234567", self.db)[0]["matched_epic"], "ABC1234567")

    def test_missing(self):
        self.assertEqual(electors.lookup("ZZZ0000000", self.db), [])
        self.assertEqual(electors.lookup("", self.db), [])
        self.assertEqual(electors.lookup("ABC1234567", Path(self.dir.name) / "none.db"), [])


if __name__ == "__main__":
    unittest.main()
