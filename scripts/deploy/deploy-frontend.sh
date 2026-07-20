#!/usr/bin/env bash
set -Eeuo pipefail

readonly BOMI_SOURCE_DIR="${BOMI_SOURCE_DIR:-$(git rev-parse --show-toplevel)}"
readonly BOMI_ENV_FILE="${BOMI_ENV_FILE:-/home/ubuntu/bomi/secrets/production.env}"
readonly BOMI_RELEASE_BRANCH="${BOMI_RELEASE_BRANCH:-fe-main}"
source "$BOMI_SOURCE_DIR/scripts/deploy/deploy-common.sh"

initialize_deploy
verify_release_commit "$BOMI_RELEASE_BRANCH"
deploy_log "Deploying Frontend commit $GIT_SHA from $BOMI_RELEASE_BRANCH"
set_env_value FRONTEND_IMAGE_TAG "$GIT_SHA"
compose config --quiet
compose build frontend
compose up -d --wait --wait-timeout 60 frontend
verify_container_health bomi-frontend
curl --fail --silent --show-error --retry 5 --retry-delay 2 \
  "https://$BOMI_DOMAIN/" >/dev/null
deploy_log "Frontend deployment completed successfully: $GIT_SHA"
