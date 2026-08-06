-- reset-demo.sql — 리허설/시연 사이에 로봇 시나리오 상태를 초기화한다.
--
-- 왜 존재하는가
--   COMPLETED 가 아닌 모든 시나리오 종료(FAILED/CANCELLED/TIMED_OUT)는 robot.current_mode 를
--   SAFE_STOP 으로 만들고, 이후 모든 이동 시나리오가 차단된다. 자동 복구 경로는 코드에
--   존재하지 않고(모든 IDLE 복귀는 SCENARIO_ACTIVE 가드 뒤에 있다), 운영자 복구 REST 는
--   OPERATOR_SHARED_SECRET 미설정 시 503 이다. 또 NAVIGATING 으로 남은 시나리오 하나가
--   ACTIVE_SCENARIO_EXISTS 로 다음 시도를 전부 거절한다 — 리허설 한 번 삐끗하면 20분간
--   아무것도 못 한다. 이 스크립트가 그 두 가지를 한 번에 푼다.
--
-- 언제 실행하는가
--   각 리허설 사이. 시연 직전. 로봇이 반응하지 않을 때 (조용한 차단은 로그에만 남는다).
--
-- 주의
--   * 진행 중인 시나리오가 없는 시점에 실행한다 (워치독/오케스트레이터가 FOR UPDATE 로
--     같은 행을 잡을 수 있다).
--   * robot 테이블에는 FK/CHECK/트리거가 없어 이 UPDATE 는 안전하다 (조사로 확인:
--     V1__init.sql, 마이그레이션 18개 전수 grep).
--   * active_navigation_command_id / active_navigation_target 은 둘 다 NULL 이거나 둘 다
--     NOT NULL 이어야 한다 (ck_scenario_active_navigation_pair).

BEGIN;

-- 1) 활성 시나리오 전부 종료 — 이게 없으면 ACTIVE_SCENARIO_EXISTS 가 계속 막는다
UPDATE scenario
   SET final_status = 'CANCELLED',
       updated_at = now(),
       active_navigation_command_id = NULL,
       active_navigation_target     = NULL
 WHERE final_status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT');

-- 2) 로봇 모드 복구 — SAFE_STOP / 고착된 SCENARIO_ACTIVE 를 IDLE 로
UPDATE robot
   SET current_mode = 'IDLE'
 WHERE device_id = 'bomi-AA001'
   AND is_active = TRUE;

COMMIT;

-- (선택) 같은 웨이크워드 eventId 를 재사용해 재시험하려면 영수증도 지운다.
--   같은 eventId 는 WakeWordCallOrchestrator 가 멱등 처리로 조용히 무시하기 때문.
-- DELETE FROM wake_word_trigger_receipt WHERE event_id = '<재사용할 eventId>';
