#!/usr/bin/env bash
set -euo pipefail

import_dir="/home/ubuntu/bomi/import/public-health-20260727"

if [[ "$(realpath -- "$import_dir")" != "/home/ubuntu/bomi/import/public-health-20260727" ]]; then
  echo "Unexpected import directory: $import_dir" >&2
  exit 1
fi

docker exec -i bomi-postgres \
  psql -v ON_ERROR_STOP=1 -U bomi -d bomi \
  < "$import_dir/01_create_stage.sql"

docker exec -i bomi-postgres \
  psql -v ON_ERROR_STOP=1 -U bomi -d bomi \
  -c "\copy public_data_raw_load_20260727.hospital FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')" \
  < "$import_dir/hospital.csv"

docker exec -i bomi-postgres \
  psql -v ON_ERROR_STOP=1 -U bomi -d bomi \
  -c "\copy public_data_raw_load_20260727.drug_permit FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')" \
  < "$import_dir/drug_permit.csv"

docker exec -i bomi-postgres \
  psql -v ON_ERROR_STOP=1 -U bomi -d bomi \
  -c "\copy public_data_raw_load_20260727.pharmacy FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')" \
  < "$import_dir/pharmacy.csv"

docker exec bomi-postgres \
  psql -v ON_ERROR_STOP=1 -U bomi -d bomi \
  -c "
    SELECT 'hospital' AS dataset, count(*) AS actual_rows, 79777 AS expected_rows
    FROM public_data_raw_load_20260727.hospital
    UNION ALL
    SELECT 'drug_permit', count(*), 42952
    FROM public_data_raw_load_20260727.drug_permit
    UNION ALL
    SELECT 'pharmacy', count(*), 25759
    FROM public_data_raw_load_20260727.pharmacy
    ORDER BY dataset;
  "
