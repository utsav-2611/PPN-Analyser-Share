# Electoral roll database

Put your electoral roll database here as `electors.db` (SQLite). It is **never committed**: this folder's contents are ignored
by git, except this note.

The DOB checks use it to verify voter ID numbers (EPIC). Without it, DOB requests that depend on a voter ID or an electoral
roll certificate go to HOLD with a clear message; everything else works as usual.

## Required format

A table named `electors` (more columns are allowed and ignored):

| column | meaning |
|---|---|
| `ac_no`, `part_no`, `serial_no` | assembly constituency, part and serial number (primary key together) |
| `ac_name` | constituency name |
| `epic` | voter ID number, for example `ABC1234567` or the old style `HR/12/123/456789` (indexed) |
| `name`, `relation_type`, `relation_name` | elector name, relation (father / husband ...) and relation name |
| `house_no`, `gender` | |
| `age` | age in the roll |
| `age_as_on` | date of that age, written `dd-mm-yyyy` |
| `deleted` | 1 if the entry is marked deleted, otherwise 0 |

```sql
CREATE TABLE electors (
  ac_no INTEGER, ac_name TEXT, part_no INTEGER, serial_no INTEGER,
  epic TEXT, name TEXT, relation_type TEXT, relation_name TEXT,
  house_no TEXT, age INTEGER, gender TEXT, age_as_on TEXT,
  deleted INTEGER DEFAULT 0,
  PRIMARY KEY (ac_no, part_no, serial_no)
);
CREATE INDEX ix_epic ON electors(epic);
```

EPICs are matched ignoring spaces, case and slashes, and also with a leading zero added to, or removed from, the last
number. To keep the database somewhere else, set `electors_db` in `config.yaml`.
