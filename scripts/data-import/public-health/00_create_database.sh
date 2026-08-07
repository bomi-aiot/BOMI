#!/usr/bin/env bash
set -euo pipefail

container_name="bomi-postgres"
target_database="${PUBLIC_HEALTH_DB_NAME:-public_health_temp}"

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

if [[ "$database_exists" == "1" ]]; then
  echo "Target database already exists: $target_database" >&2
  exit 1
fi

docker exec "$container_name" \
  createdb -U "$postgres_user" -O "$postgres_user" "$target_database"

docker exec "$container_name" \
  psql -U "$postgres_user" -d "$target_database" -Atc \
  "SELECT current_database(), current_user"
