#!/usr/bin/env bash
#
# BOMI DB 덤프 생성·검증 스크립트 (포팅 매뉴얼 ③ 제출용)
#
#   사용법:  exec/scripts/dump-db.sh [옵션]
#
#   옵션:
#     --reset       덤프 직전에 scripts/dev/reset-demo.sql 을 적용한다.
#                   (SAFE_STOP 해제 + 잔여 ACTIVE 시나리오 정리 → '시연 가능한 상태'로 덤프)
#     --no-verify   복원 검증을 건너뛴다. (권장하지 않음)
#     --out DIR     출력 디렉터리. 기본값은 저장소의 exec/
#
#   하는 일:
#     1) 사전 점검 (컨테이너 healthy, 환경파일 가독)
#     2) (--reset) reset-demo.sql 적용
#     3) pg_dump 로 평문 SQL 덤프 생성 (--no-owner --no-privileges)
#     4) 덤프 맨 앞에 메타 헤더 주입 (커밋 SHA / 생성시각 / PG·pgvector 버전)
#     5) ★ 같은 컨테이너 안에 임시 DB 를 만들어 실제로 복원해 보고 검증한 뒤 삭제
#
#   왜 평문 SQL(-Fc 아님)인가
#     심사자가 pg_restore 없이 `psql -f` 한 줄로 복원할 수 있어야 한다.
#     시연 데이터 규모에서는 용량 이점보다 복원 편의가 중요하다.
#
set -Eeuo pipefail

# ── 설정 ────────────────────────────────────────────────────────────────────
CONTAINER="${BOMI_PG_CONTAINER:-bomi-postgres}"
ENV_FILE="${BOMI_ENV_FILE:-/home/ubuntu/bomi/secrets/production.env}"
REPO_DIR="${BOMI_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
OUT_DIR="$REPO_DIR/exec"
DO_RESET=0
DO_VERIFY=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset)      DO_RESET=1; shift ;;
    --no-verify)  DO_VERIFY=0; shift ;;
    --out)        OUT_DIR="$2"; shift 2 ;;
    -h|--help)    sed -n '2,30p' "$0"; exit 0 ;;
    *)            echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done

log()  { printf '[dump] %s\n' "$*"; }
fail() { printf '[dump] ERROR: %s\n' "$*" >&2; exit 1; }
trap 'printf "[dump] FAILED at line %s\n" "$LINENO" >&2' ERR

# ── 1. 사전 점검 ────────────────────────────────────────────────────────────
command -v docker >/dev/null || fail 'docker 가 없습니다'
docker inspect "$CONTAINER" >/dev/null 2>&1 || fail "컨테이너를 찾을 수 없습니다: $CONTAINER"

health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER")"
[[ "$health" == 'healthy' || "$health" == 'running' ]] \
  || fail "$CONTAINER 상태가 정상이 아닙니다 (현재: $health)"

PGUSER_VAL="$(docker exec "$CONTAINER" printenv POSTGRES_USER)"
PGDB_VAL="$(docker exec "$CONTAINER" printenv POSTGRES_DB)"
[[ -n "$PGUSER_VAL" && -n "$PGDB_VAL" ]] || fail 'POSTGRES_USER / POSTGRES_DB 를 읽지 못했습니다'
log "대상: 컨테이너=$CONTAINER  DB=$PGDB_VAL  사용자=$PGUSER_VAL"

mkdir -p "$OUT_DIR"

# ── 2. (선택) 시연 상태로 초기화 ────────────────────────────────────────────
if [[ "$DO_RESET" -eq 1 ]]; then
  RESET_SQL="$REPO_DIR/scripts/dev/reset-demo.sql"
  [[ -r "$RESET_SQL" ]] || fail "reset-demo.sql 을 읽을 수 없습니다: $RESET_SQL"
  log 'reset-demo.sql 적용 (SAFE_STOP 해제 + 잔여 시나리오 정리)'
  docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -q \
    -U "$PGUSER_VAL" -d "$PGDB_VAL" < "$RESET_SQL"
fi

# ── 3. 덤프 생성 ────────────────────────────────────────────────────────────
STAMP="$(date +%Y%m%d-%H%M)"
OUT_FILE="$OUT_DIR/bomi-dump-${STAMP}.sql"
TMP_BODY="$(mktemp)"
trap 'rm -f "$TMP_BODY"' EXIT

log "덤프 생성 중 → $(basename "$OUT_FILE")"
#   --no-owner       복원 대상의 롤 이름이 달라도 되도록 소유자 지정을 뺀다
#   --no-privileges  GRANT/REVOKE 제거 (같은 이유)
#   --clean --if-exists  기존 객체가 있어도 복원이 진행되도록
#   --quote-all-identifiers  예약어 충돌 방지
docker exec "$CONTAINER" pg_dump \
  -U "$PGUSER_VAL" -d "$PGDB_VAL" \
  --no-owner --no-privileges \
  --clean --if-exists \
  --quote-all-identifiers \
  > "$TMP_BODY"

[[ -s "$TMP_BODY" ]] || fail '덤프가 비어 있습니다'

# ── 4. 메타 헤더 주입 ───────────────────────────────────────────────────────
GIT_SHA='(unknown)'
if git -C "$REPO_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  GIT_SHA="$(git -C "$REPO_DIR" rev-parse --short=12 HEAD)"
fi
PG_VER="$(docker exec "$CONTAINER" psql -tA -U "$PGUSER_VAL" -d "$PGDB_VAL" \
          -c 'SHOW server_version;')"
VEC_VER="$(docker exec "$CONTAINER" psql -tA -U "$PGUSER_VAL" -d "$PGDB_VAL" \
          -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
FLYWAY_VER="$(docker exec "$CONTAINER" psql -tA -U "$PGUSER_VAL" -d "$PGDB_VAL" \
          -c "SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank DESC LIMIT 1;" \
          2>/dev/null || echo '(none)')"

{
  echo "-- ============================================================"
  echo "-- BOMI DB 덤프"
  echo "--   생성 시각   : $(date --iso-8601=seconds)"
  echo "--   기준 커밋   : $GIT_SHA"
  echo "--   PostgreSQL  : $PG_VER"
  echo "--   pgvector    : ${VEC_VER:-(미설치)}"
  echo "--   Flyway 최종 : $FLYWAY_VER"
  echo "--"
  echo "-- 복원 전제: 대상 서버에 pgvector 확장이 설치되어 있어야 합니다."
  echo "--            (pgvector/pgvector:0.8.5-pg17 이미지 사용 시 충족)"
  echo "-- 복원 예시:"
  echo "--   createdb -U bomi bomi"
  echo "--   psql -U bomi -d bomi -v ON_ERROR_STOP=1 -f $(basename "$OUT_FILE")"
  echo "--"
  echo "-- 주의: 이 파일에는 API 키·비밀번호가 들어 있지 않습니다."
  echo "--       모든 시크릿은 production.env 와 각 장치의 .env 에만 존재합니다."
  echo "-- ============================================================"
  echo
  cat "$TMP_BODY"
} > "$OUT_FILE"

log "생성 완료: $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"

# ── 5. 복원 검증 (임시 DB 왕복) ─────────────────────────────────────────────
if [[ "$DO_VERIFY" -eq 0 ]]; then
  log '검증 생략 (--no-verify)'
  exit 0
fi

VERIFY_DB="bomi_dumpcheck_$$"
log "복원 검증 시작 → 임시 DB $VERIFY_DB"

cleanup_verify() {
  docker exec "$CONTAINER" psql -q -U "$PGUSER_VAL" -d postgres \
    -c "DROP DATABASE IF EXISTS \"$VERIFY_DB\";" >/dev/null 2>&1 || true
}
trap 'cleanup_verify; rm -f "$TMP_BODY"' EXIT

docker exec "$CONTAINER" psql -q -U "$PGUSER_VAL" -d postgres \
  -c "CREATE DATABASE \"$VERIFY_DB\";"

# ON_ERROR_STOP=1 이 핵심이다. 없으면 절반이 실패해도 종료코드가 0 이라
# "복원됐다"고 착각한다.
if ! docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -q \
      -U "$PGUSER_VAL" -d "$VERIFY_DB" < "$OUT_FILE" > /tmp/bomi-restore.log 2>&1; then
  tail -20 /tmp/bomi-restore.log >&2
  fail '복원 검증 실패 — 위 오류를 확인하세요'
fi

vq() { docker exec "$CONTAINER" psql -tA -U "$PGUSER_VAL" -d "$VERIFY_DB" -c "$1"; }

SRC_TABLES="$(docker exec "$CONTAINER" psql -tA -U "$PGUSER_VAL" -d "$PGDB_VAL" \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
DST_TABLES="$(vq "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
DST_VEC="$(vq "SELECT coalesce(extversion,'') FROM pg_extension WHERE extname='vector';")"
DST_FLYWAY="$(vq "SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank DESC LIMIT 1;" 2>/dev/null || echo '')"

echo
echo "  ── 검증 결과 ──────────────────────────────"
printf '  %-22s 원본 %s / 복원 %s\n' '테이블 수' "$SRC_TABLES" "$DST_TABLES"
printf '  %-22s %s\n' 'pgvector 확장' "${DST_VEC:-없음}"
printf '  %-22s %s\n' 'Flyway 최종 버전' "${DST_FLYWAY:-없음}"

# 주요 테이블 행 수 대조 (존재하는 것만)
for t in app_user robot senior memory conversation conversation_summary care_record; do
  exists="$(vq "SELECT to_regclass('public.$t') IS NOT NULL;")"
  [[ "$exists" == 't' ]] || continue
  s="$(docker exec "$CONTAINER" psql -tA -U "$PGUSER_VAL" -d "$PGDB_VAL" -c "SELECT count(*) FROM \"$t\";")"
  d="$(vq "SELECT count(*) FROM \"$t\";")"
  status='OK'; [[ "$s" == "$d" ]] || status='!! 불일치'
  printf '  %-22s 원본 %-6s 복원 %-6s %s\n' "$t" "$s" "$d" "$status"
  [[ "$s" == "$d" ]] || fail "$t 행 수가 다릅니다"
done
echo "  ───────────────────────────────────────────"
echo

[[ "$SRC_TABLES" == "$DST_TABLES" ]] || fail '테이블 수가 다릅니다'
[[ -n "$DST_VEC" ]] || fail 'pgvector 확장이 복원되지 않았습니다'

log '✅ 복원 검증 통과'
log "제출 파일: $OUT_FILE"
