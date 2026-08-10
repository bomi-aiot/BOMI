-- reset-demo-data.sql — 테스트 잔여 데이터를 지운다. **시드는 남긴다.**
--
-- ─────────────────────────────────────────────────────────────────────────────
-- reset-demo.sql 과 무엇이 다른가
--
--   reset-demo.sql 은 **로봇을 다시 움직이게** 만든다. SAFE_STOP 을 풀고,
--   ACTIVE_SCENARIO_EXISTS 를 풀고, 복약 슬롯 영수증을 무효화하고, 지난 T1 을 닫는다.
--   행을 거의 지우지 않는다 — 무엇이 언제 돌았는지 되짚을 근거를 남기려고 그렇게 했다.
--
--   이 파일은 **화면을 비운다.** 어제 리허설이 남긴 대화·확인 요청·기억·일정을 지우고,
--   시드만 남은 상태로 되돌린다. 새 시연을 깨끗하게 시작할 때 쓴다.
--
--   둘은 보완 관계다. 보통 이 파일을 먼저 돌리고 reset-demo.sql 을 돌린다.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- ★ 시드와 잔여물을 무엇으로 가르는가 — 고정 UUID
--
--   seed-*.sql 이 넣는 행은 전부 손으로 적은 고정 UUID 다:
--     10000000-0000-4000-8000-000000000001   (어르신)
--     40000000-0000-4000-8000-00000000000a   (회상 기억)
--     80000000-0000-4000-8000-000000000001   (복약)
--   2·3·4번째 블록이 `0000-4000-8000` 으로 고정돼 있다.
--
--   반면 대화·화면에서 생기는 행은 UUIDv4 다:
--     c8fe92b3-2b6e-496c-a09b-be78d911cae6
--   세 블록이 난수라 위 패턴에 걸릴 확률은 7000억 분의 1이다.
--
--   그래서 `id::text NOT LIKE '%-0000-4000-8000-%'` 하나로 갈린다.
--   2026-08-10 실측: 복약 2건 중 시드 1·테스트 1, 일정 2건 전부 테스트,
--   확인 요청 3건 전부 테스트, 기억 31건 중 시드 12·테스트 19.
--
--   ⚠️ 시드를 새로 추가할 때는 반드시 이 UUID 패턴을 쓴다. 랜덤 UUID 로 넣은 '시드'는
--      이 스크립트가 잔여물로 보고 지운다.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 정본은 여기가 아니다
--
--   실제로 운영자가 누르는 것은 DB 뷰어(Streamlit)의 "② 삭제" 버튼이고, 그 SQL 은
--   backend/tools/db_viewer/reset_actions.py 의 RESIDUE_DELETE_TARGETS 에 있다.
--   도커 빌드 컨텍스트 제약으로 파일을 공유할 수 없어 여기에 옮겨 적었다.
--   복붙은 반드시 갈라지므로 tests/test_reset_actions.py 가 두 곳을 대조해
--   어긋나면 실패한다 — reset-demo.sql 과 같은 방식이다.
--
-- 실행
--   psql "$DATABASE_URL" -f scripts/dev/reset-demo-data.sql
--
-- 지우지 않는 것
--   app_user / care_relationship / robot   신원·관계·기기 등록. 지우면 시연 불가
--   onboarding_session / onboarding_answer 지우면 로봇이 온보딩부터 다시 시작한다
--   drug_permit / hospital / pharmacy      외부 의료 마스터 14만 행. 재적재 불가
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- 1) 보호자 화면에 보이는 것 — 시드만 남기고 지운다 ─────────────────────────
--
--   care_record 하나에 복약·복약슬롯·일정·위급알림·건강관찰이 record_type 으로만
--   갈려 전부 들어 있다. 이 한 줄이 화면 세 블록(복약 관리·오늘의 복약 응답·
--   일정 관리)을 동시에 정리한다.
DELETE FROM care_record    WHERE id::text NOT LIKE '%-0000-4000-8000-%';

--   "확인할 일" 카드의 출처. 이름 때문에 conversation 계열로 착각하기 쉽지만
--   fact_candidate 다 (backend/CLAUDE.md §2 — 같은 테이블을 로봇용/가디언웹용
--   컨트롤러로 나눠 놓았다).
DELETE FROM fact_candidate WHERE id::text NOT LIKE '%-0000-4000-8000-%';

--   활동 피드의 "새로 기억한 내용". 시드(회상 재료)는 남고 대화로 생긴 것만 지운다.
DELETE FROM memory         WHERE id::text NOT LIKE '%-0000-4000-8000-%';
DELETE FROM known_person   WHERE id::text NOT LIKE '%-0000-4000-8000-%';

-- 2) 실행 흔적 — 전량 삭제 ──────────────────────────────────────────────────
--
--   시드가 없다. 전부 실행 중에 생기므로 남겨 둘 이유가 없다.
--   FK 가 하나도 없는 스키마라(마이그레이션 20개 전수 확인) 부모만 지우면 자식이
--   고아로 남는다 — conversation 세 개를 반드시 함께 지운다.
DELETE FROM conversation_message;
DELETE FROM conversation_summary;
DELETE FROM conversation;
DELETE FROM scenario;
DELETE FROM wake_word_trigger_receipt;
DELETE FROM robot_mode_recovery_audit;
DELETE FROM operator_scenario_cancellation_audit;
DELETE FROM occupancy_event;
DELETE FROM daily_activity_metric;
DELETE FROM walk_request_receipt;

-- 3) 지울 '행'이 없는 것 ────────────────────────────────────────────────────
--
--   "집 안 온도와 습도" 카드는 robot 한 행의 컬럼 세 개를 읽는다. IoT 관측이 올 때마다
--   덮어써지므로 어떤 DELETE 로도 사라지지 않는다 — "삭제했는데 온습도가 그대로다"의
--   답이 이것이다.
--
--   ★ 파이(dht11)가 켜져 있으면 몇 초 안에 새 값이 다시 들어온다. 고장이 아니다.
--     화면을 진짜로 비우려면 퍼블리셔를 먼저 끈다.
UPDATE robot
   SET ambient_temperature_c    = NULL,
       ambient_humidity_percent = NULL,
       ambient_observed_at      = NULL
 WHERE is_active = TRUE;

COMMIT;


-- ─────────────────────────────────────────────────────────────────────────────
-- 확인 — 시드만 남았는지 본다. '잔여' 열이 전부 0 이어야 한다.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT '확인할 일(fact_candidate)' AS 항목,
       count(*) FILTER (WHERE id::text LIKE '%-0000-4000-8000-%')     AS 시드,
       count(*) FILTER (WHERE id::text NOT LIKE '%-0000-4000-8000-%') AS 잔여
  FROM fact_candidate
UNION ALL
SELECT '복약·일정(care_record)',
       count(*) FILTER (WHERE id::text LIKE '%-0000-4000-8000-%'),
       count(*) FILTER (WHERE id::text NOT LIKE '%-0000-4000-8000-%')
  FROM care_record
UNION ALL
SELECT '기억(memory)',
       count(*) FILTER (WHERE id::text LIKE '%-0000-4000-8000-%'),
       count(*) FILTER (WHERE id::text NOT LIKE '%-0000-4000-8000-%')
  FROM memory;


-- ─────────────────────────────────────────────────────────────────────────────
-- 로봇도 함께 — DB 만 지우면 절반이다
--
--   ai_chat 은 자기 SQLite 에 운영 상태를 따로 들고 있다. 백엔드 DB 를 비운 뒤 로봇을
--   그대로 두면, 로봇이 **백엔드에 이미 없는 conversation_id 를 계속 붙여 보낸다.**
--   백엔드는 그때마다 400 `unknown conversationId` 로 거절하고, 그 턴의 발화는 어디에도
--   기록되지 않는다 — 화면에는 "아무 일도 없었던 것"으로 보인다(2026-08-10 실측).
--
--     cd robot/ai_chat
--     python -c "import sqlite3; c=sqlite3.connect('var/localstore/runtime.sqlite'); \
--       c.execute('update runtime_state set conversation_id=NULL'); \
--       c.execute('delete from checkpoints'); c.execute('delete from writes'); c.commit()"
-- ─────────────────────────────────────────────────────────────────────────────
