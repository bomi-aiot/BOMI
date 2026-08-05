#!/usr/bin/env bash

compose() {
  docker compose --env-file "$BOMI_ENV_FILE" -f "$BOMI_COMPOSE_FILE" "$@"
}

deploy_log() {
  printf '[deploy] %s\n' "$*"
}

deploy_fail() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

read_env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$BOMI_ENV_FILE"
}

# 값이 반드시 있어야 하는 환경변수를 읽는다. 없으면 실패한다.
#
# 왜 함수로 뽑았는가
#   같은 검사가 세 곳에 손으로 적혀 있었다(initialize_deploy 의 BOMI_DOMAIN,
#   deploy-production.sh, 그리고 이 티켓이 추가한 것). 메시지 문구도 셋이 달랐다.
#   다음 필수 변수를 추가하는 사람이 어느 모양을 베낄지 동전을 던지게 된다.
require_env() {
  local key="$1" value
  value="$(read_env_value "$key")"
  [[ -n "$value" ]] || deploy_fail "$key is missing from $BOMI_ENV_FILE"
  printf '%s' "$value"
}

# 호스트 경로여야 하는 환경변수를 검증한다. (S15P11E102-218)
#
# 왜 필요한가
#   compose 의 볼륨 짧은 문법은 콜론으로 필드를 쪼갠다. 값이 경로가 아니면 첫 조각이
#   '이름 있는 볼륨'으로 해석되고, 오류에 변수 이름이 등장하지 않는다. 실제로 한 번
#   겪었다 — 경위와 각 변수에 무엇을 넣어야 하는지는 infra/production.env.example 에
#   있다. 여기서 다시 설명하지 않는다(CLAUDE.md §21: 재설명보다 상호 참조).
#
# 메시지를 변수별로 특화하지 않는다
#   전에는 이 함수가 Qdrant 전용 안내를 담고 있었다. POSTGRES_DATA_DIR 로 발동하면
#   "예: POSTGRES_DATA_DIR=<qdrant 경로>" 를 출력했고, 그것을 복사하는 운영자는
#   권위 DB 를 파생 인덱스 디렉터리로 지정한다. 파괴적인 조언을 하는 가드는 없는
#   가드보다 나쁘다. 변수별 안내는 env.example 이 갖는다.
require_absolute_path() {
  local key="$1" value
  value="$(require_env "$key")"
  [[ "$value" == /* ]] || deploy_fail     "$key must be an absolute host path, not '$value' — see infra/production.env.example"
}

set_env_value() {
  local key="$1" value="$2" temporary_file
  temporary_file="$(mktemp "${BOMI_ENV_FILE}.tmp.XXXXXX")"
  chmod 600 "$temporary_file"
  awk -F= -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    $1 == key { print key "=" value; updated = 1; next }
    { print }
    END { if (!updated) print key "=" value }
  ' "$BOMI_ENV_FILE" > "$temporary_file"
  mv "$temporary_file" "$BOMI_ENV_FILE"
}

verify_release_commit() {
  local release_branch="$1" head_commit release_commit
  head_commit="$(git rev-parse HEAD)"
  release_commit="$(git rev-parse "refs/remotes/origin/$release_branch")" \
    || deploy_fail "origin/$release_branch is not available"
  [[ "$head_commit" == "$release_commit" ]] \
    || deploy_fail "HEAD is not the latest origin/$release_branch commit"
}

initialize_deploy() {
  command -v git >/dev/null 2>&1 || deploy_fail 'git is not installed'
  command -v docker >/dev/null 2>&1 || deploy_fail 'docker is not installed'
  command -v curl >/dev/null 2>&1 || deploy_fail 'curl is not installed'
  [[ -d "$BOMI_SOURCE_DIR/.git" ]] || deploy_fail "Git repository not found: $BOMI_SOURCE_DIR"
  [[ -r "$BOMI_ENV_FILE" ]] || deploy_fail "Environment file not readable: $BOMI_ENV_FILE"
  cd "$BOMI_SOURCE_DIR"
  [[ -z "$(git status --porcelain)" ]] || deploy_fail 'Git working tree is not clean'
  BOMI_COMPOSE_FILE="$BOMI_SOURCE_DIR/infra/compose.prod.yml"
  [[ -r "$BOMI_COMPOSE_FILE" ]] || deploy_fail "Compose file not readable: $BOMI_COMPOSE_FILE"
  GIT_SHA="$(git rev-parse --short=12 HEAD)"
  BOMI_DOMAIN="$(require_env BOMI_DOMAIN)"

  # 경로 변수를 여기서 본다. 부수효과보다 먼저다.
  #
  # 왜 배포 스크립트가 아니라 여기인가
  #   (1) compose config 는 프로젝트 '전체'를 검증한다. 그래서 잘못된 QDRANT 경로가
  #       프론트엔드 배포도 같은 오류로 죽인다 — Qdrant 와 무관한 스크립트에서.
  #       공용 함수에 두면 deploy-common.sh 를 source 하는 모든 스크립트가 덮인다.
  #   (2) deploy-backend.sh 는 set_env_value 로 시크릿 파일을 먼저 고친다. 그 뒤에
  #       검증이 실패하면 BACKEND_IMAGE_TAG 가 '빌드된 적 없는 이미지'를 가리킨 채
  #       남고, 다음 compose up 이 그것을 읽는다.
  #
  # 목록이 손으로 관리된다는 것이 이 방식의 약점이다. compose 에 새 bind mount 가
  # 추가되면 여기도 늘어야 하고, 그 표류는 ComposeEnvironmentPassthroughTest 의
  # everyBindMountSourceIsGuarded 가 잡는다.
  require_absolute_path POSTGRES_DATA_DIR
  require_absolute_path JENKINS_HOME_DIR
  require_absolute_path CERTBOT_CONF_DIR
  require_absolute_path CERTBOT_WEBROOT_DIR
  # 가디언웹 채널 단기 접근 제어용 htpasswd 파일 (S15P11E102-310) — 2026-08-05
  # 임시 보류. compose.prod.yml 의 바인드 마운트 자체를 주석 처리했으므로 여기서
  # 검증할 대상이 없다. 되살리는 절차는 infra/README.md, compose.prod.yml 참고.
  # require_absolute_path NGINX_GUARDIAN_HTPASSWD_FILE
}

verify_container_health() {
  local container="$1" health
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")"
  [[ "$health" == healthy ]] || deploy_fail "$container is not healthy (state: $health)"
}

# 공용 Nginx 에 새 설정을 적용한다.
#
# 왜 필요한가
#   nginx 설정은 이미지에 굽지 않고 이 저장소의 infra/nginx/conf.d 를 그대로
#   마운트한다(compose.prod.yml). 그래서 배포 때 checkout 만으로 파일은 새것이
#   되지만, 실행 중인 nginx 는 시작 시점에 읽은 설정을 계속 쓴다.
#
#   이게 없으면 무엇이 조용히 깨지는가
#   허용 경로를 추가해도 반영되지 않고, 그 경로 요청은 fallback 인 프론트엔드로
#   넘어가 200 + SPA HTML 을 돌려준다. 상태 코드만 보면 정상처럼 보여서
#   "배포됐다"고 오판하기 쉽다. 실제로 그렇게 한 번 놓쳤다.
#
# 컨테이너를 재생성하지 않는 이유
#   reload 는 무중단이고 설정이 잘못돼도 기존 프로세스가 그대로 살아 있다.
#   --force-recreate 는 짧게라도 502 를 만든다.
reload_nginx_config() {
  local container="${1:-bomi-nginx}" running

  running="$(docker inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)"
  if [[ "$running" != true ]]; then
    deploy_log "$container is not running; skipping nginx reload"
    return 0
  fi

  # 검증을 먼저 한다. 잘못된 설정으로 reload 하면 nginx 는 살아남지만 새 설정이
  # 적용되지 않은 채 배포가 성공으로 끝나 버린다.
  docker exec "$container" nginx -t \
    || deploy_fail "$container has an invalid configuration; not reloading"
  docker exec "$container" nginx -s reload \
    || deploy_fail "$container failed to reload its configuration"
  deploy_log "$container reloaded its configuration"
}
