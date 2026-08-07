#!/usr/bin/env bash
set -euo pipefail

import_dir="/home/ubuntu/bomi/import/public-health-20260727"
container_name="bomi-postgres"
target_database="${PUBLIC_HEALTH_DB_NAME:-public_health_temp}"

if [[ "$(realpath -- "$import_dir")" != "/home/ubuntu/bomi/import/public-health-20260727" ]]; then
  echo "Unexpected import directory: $import_dir" >&2
  exit 1
fi

if [[ ! "$target_database" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "Invalid database name: $target_database" >&2
  exit 1
fi

postgres_user="$(docker exec "$container_name" printenv POSTGRES_USER)"

if [[ -z "$postgres_user" ]]; then
  echo "POSTGRES_USER is not set in $container_name" >&2
  exit 1
fi

database_exists="$(
  docker exec "$container_name" \
    psql -U "$postgres_user" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$target_database'"
)"

if [[ "$database_exists" != "1" ]]; then
  echo "Target database does not exist: $target_database" >&2
  exit 1
fi

docker exec -i "$container_name" \
  psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$target_database" \
  < "$import_dir/01_create_stage.sql"

docker exec -i "$container_name" \
  psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$target_database" \
  -c "\copy public_data_raw_load_20260727.hospital FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')" \
  < "$import_dir/hospital.csv"

docker exec -i "$container_name" \
  psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$target_database" \
  -c "\copy public_data_raw_load_20260727.drug_permit FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')" \
  < "$import_dir/drug_permit.csv"

docker exec -i "$container_name" \
  psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$target_database" \
  -c "\copy public_data_raw_load_20260727.pharmacy FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')" \
  < "$import_dir/pharmacy.csv"

docker exec "$container_name" \
  psql -v ON_ERROR_STOP=1 -U "$postgres_user" -d "$target_database" \
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
