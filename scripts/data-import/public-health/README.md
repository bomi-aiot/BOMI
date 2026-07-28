# Public health data one-time import

This runbook imports the 2026-07-27 hospital, drug permit, and pharmacy
spreadsheets into an isolated PostgreSQL schema without uploading the source
XLSX files to EC2.

## Safety boundary

- Source XLSX files are read only and stay on the local machine.
- EC2 receives three generated UTF-8 CSV files and these SQL scripts only.
- PostgreSQL is backed up before schema creation.
- Data is loaded into `public_data_raw_load_20260727` first.
- `02_promote.sql` refuses promotion unless all three row counts match.
- An existing `public_data_raw` schema is never overwritten.
- EC2 import files are removed only after final verification succeeds.

## Expected source shape

| Dataset | Source columns | Data rows |
| --- | ---: | ---: |
| Hospital | 30 | 79,777 |
| Drug permit | 21 | 42,952 |
| Pharmacy | 15 | 25,759 |

All source columns use PostgreSQL `text` so codes, identifiers, postal codes,
and `YYYYMMDD` source values are not changed during the raw import.

## EC2 temporary path

```text
/home/ubuntu/bomi/import/public-health-20260727/
```

After successful verification, remove only the seven known temporary files and
then remove the empty directory.
