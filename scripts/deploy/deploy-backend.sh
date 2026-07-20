#!/usr/bin/env bash
set -Eeuo pipefail

readonly BOMI_SOURCE_DIR="${BOMI_SOURCE_DIR:-$(git rev-parse --show-toplevel)}"
readonly BOMI_ENV_FILE="${BOMI_ENV_FILE:-/home/ubuntu/bomi/secrets/production.env}"
readonly BOMI_RELEASE_BRANCH="${BOMI_RELEASE_BRANCH:-be-main}"
source "$BOMI_SOURCE_DIR/scripts/deploy/deploy-common.sh"

initialize_deploy
verify_release_commit "$BOMI_RELEASE_BRANCH"
deploy_log "Deploying Backend commit $GIT_SHA from $BOMI_RELEASE_BRANCH"
set_env_value BACKEND_IMAGE_TAG "$GIT_SHA"
compose config --quiet
compose up -d --wait --wait-timeout 60 postgres
compose build backend
compose up -d --wait --wait-timeout 120 backend
verify_container_health bomi-postgres
verify_container_health bomi-backend
curl --fail --silent --show-error --retry 5 --retry-delay 2 \
  "https://$BOMI_DOMAIN/api/health" >/dev/null
deploy_log "Backend deployment completed successfully: $GIT_SHA"
