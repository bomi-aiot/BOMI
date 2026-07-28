# Public health data one-time import

This runbook imports the 2026-07-27 hospital, drug permit, and pharmacy
spreadsheets into the `public` schema of a separate PostgreSQL database named
`public_health_temp`.

The BOMI application database remains `bomi`; these scripts never change the
Backend `POSTGRES_DB` setting.

## Safety boundary

- Source XLSX files are read only and are not uploaded to EC2 or committed.
- EC2 receives three generated UTF-8 CSV files and the import scripts only.
- PostgreSQL is backed up before database creation.
- `00_create_database.sh` refuses to overwrite an existing database.
- Data is loaded into `public_data_raw_load_20260727` inside the target
  database first.
- `02_promote.sql` refuses promotion unless all three row counts match.
- Existing `public.hospital`, `public.drug_permit`, or `public.pharmacy`
  tables are never overwritten.
- EC2 import files are removed only after final verification succeeds.

## Final database structure

```text
database: public_health_temp
schema: public
tables:
  - hospital
  - drug_permit
  - pharmacy
```

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

## Execution order

Run these commands on EC2 after the CSV and script files are present in the
temporary path.

```bash
bash /home/ubuntu/bomi/import/public-health-20260727/00_create_database.sh

bash /home/ubuntu/bomi/import/public-health-20260727/04_load_stage.sh

postgres_user="$(docker exec bomi-postgres printenv POSTGRES_USER)"

docker exec -i bomi-postgres \
  psql -v ON_ERROR_STOP=1 \
  -U "$postgres_user" \
  -d public_health_temp \
  < /home/ubuntu/bomi/import/public-health-20260727/02_promote.sql

docker exec -i bomi-postgres \
  psql -v ON_ERROR_STOP=1 \
  -U "$postgres_user" \
  -d public_health_temp \
  < /home/ubuntu/bomi/import/public-health-20260727/03_verify.sql
```

The database name can be overridden for an isolated verification run:

```bash
PUBLIC_HEALTH_DB_NAME=public_health_script_test \
  bash /home/ubuntu/bomi/import/public-health-20260727/00_create_database.sh
```

After successful verification, remove only the eight known temporary files
and then remove the empty import directory.
