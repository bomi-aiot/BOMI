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
set_env_value OPERATOR_CONSOLE_IMAGE_TAG "$GIT_SHA"
set_env_value WAYPOINT_EDITOR_IMAGE_TAG "$GIT_SHA"
set_env_value DB_VIEWER_IMAGE_TAG "$GIT_SHA"
compose config --quiet
compose up -d --wait --wait-timeout 60 postgres
compose build backend operator-console waypoint-editor db-viewer
compose up -d --wait --wait-timeout 120 backend operator-console waypoint-editor db-viewer
# Nginx must be recreated the first time so the operator-console htpasswd bind
# mount is applied. On later deploys Compose leaves it running when unchanged.
compose up -d --wait --wait-timeout 60 nginx
verify_container_health bomi-postgres
# Qdrant 는 backend 의 depends_on 으로 함께 뜬다(compose up 이 의존성을 시작한다).
# 그래도 여기서 따로 확인한다 — 확인하지 않으면 Qdrant 가 불건강할 때 "backend 가
# healthy 가 되지 않았다"로만 실패하고, 원인이 색인 서버라는 사실이 로그에 없다.
verify_container_health bomi-qdrant
verify_container_health bomi-backend
verify_container_health bomi-operator-console
verify_container_health bomi-waypoint-editor
verify_container_health bomi-db-viewer
verify_container_health bomi-nginx
# 공용 Nginx 가 마운트하는 conf.d 는 이 워크스페이스의 것이다(compose.prod.yml).
# 방금 checkout 으로 파일이 바뀌었을 수 있으니 여기서 반영한다. Frontend 배포에는
# 넣지 않는다 — nginx 는 fe 워크스페이스를 마운트하지 않으므로 리로드할 이유가 없다.
reload_nginx_config
curl --fail --silent --show-error --retry 5 --retry-delay 2 \
  "https://$BOMI_DOMAIN/api/health" >/dev/null
operator_console_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "https://$BOMI_DOMAIN/operator-console/")"
[[ "$operator_console_status" == 401 ]] \
  || deploy_fail "Operator Console must reject unauthenticated requests (HTTP $operator_console_status)"
waypoint_editor_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "https://$BOMI_DOMAIN/waypoint-editor/")"
[[ "$waypoint_editor_status" == 401 ]] \
  || deploy_fail "Waypoint Editor must reject unauthenticated requests (HTTP $waypoint_editor_status)"
db_viewer_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  "https://$BOMI_DOMAIN/db-viewer/")"
[[ "$db_viewer_status" == 401 ]] \
  || deploy_fail "DB Viewer must reject unauthenticated requests (HTTP $db_viewer_status)"
deploy_log "Backend deployment completed successfully: $GIT_SHA"
