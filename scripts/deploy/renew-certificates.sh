#!/usr/bin/env bash
set -euo pipefail

BOMI_SOURCE_DIR=/home/ubuntu/bomi/deploy/source
BOMI_ENV_FILE=/home/ubuntu/bomi/secrets/production.env
BOMI_COMPOSE_FILE="$BOMI_SOURCE_DIR/infra/compose.prod.yml"

cd "$BOMI_SOURCE_DIR"

docker compose \
  --profile tools \
  --env-file "$BOMI_ENV_FILE" \
  -f "$BOMI_COMPOSE_FILE" \
  run --rm certbot renew \
  --webroot --webroot-path /var/www/certbot \
  --quiet

docker compose \
  --env-file "$BOMI_ENV_FILE" \
  -f "$BOMI_COMPOSE_FILE" \
  exec -T nginx nginx -s reload
