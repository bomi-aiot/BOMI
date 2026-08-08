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

-- 3) 복약 슬롯 영수증 무효화 — 이게 없으면 같은 약을 두 번째 리허설부터 못 울린다
--
--   MedicationReminderScheduler 는 슬롯마다 slotKey("med-{scheduleId}-{날짜}-{시각}")를
--   만들어 existsByScenarioTypeAndExternalEventId 로 "오늘 이미 알렸는지"를 판정한다.
--   판정은 final_status 가 아니라 **행의 존재 여부**만 본다 — 그래서 1) 의 CANCELLED 로는
--   풀리지 않고, 리셋 후에도 같은 시각 슬롯은 조용히 침묵한다(로그도 안 남는다).
--
--   행을 지우지 않고 키만 어긋나게 한다. scenario 를 가리키는 FK 는 하나도 없지만
--   (conversation.scenario_id 등은 전부 순수 uuid 컬럼), 삭제하면 고아 행이 생기고
--   시연 후 무엇이 언제 돌았는지 되짚을 근거도 사라진다.
--
--   external_event_id 는 varchar(255) 라 접미사 여유가 충분하고, 유니크 인덱스는
--   scenario_type = 'WAKE_WORD_CALL' 에만 걸려 있어 이 UPDATE 와 무관하다.
--   NOT LIKE 조건 덕에 여러 번 실행해도 접미사가 겹겹이 쌓이지 않는다.
UPDATE scenario
   SET external_event_id = external_event_id || '-reset'
 WHERE scenario_type = 'MEDICATION_REMINDER'
   AND external_event_id LIKE 'med-%'
   AND external_event_id NOT LIKE '%-reset';

-- 4) 지난 위급 알림(T1) 닫기 — 이게 없으면 시연 첫 화면에 어제 알림이 떠 있다
--
--   DashboardService.buildActivities 는 care_record 에서
--   record_type='GUARDIAN_ALERT' AND status='ACTIVE' 인 행을 전부 읽어 활동 피드에
--   섞고, notification_tier='T1' 인 것만 statusLevel='URGENT' 로 올린다. 프론트의
--   안전 알림 카드는 그 URGENT 만 골라 "즉시 확인 필요"로 그린다. 즉 행이
--   ACTIVE 로 남아 있는 한, 그것이 사흘 전 리허설의 잔재여도 화면은 지금 위급인
--   것처럼 보인다.
--
--   왜 DELETE 가 아니라 status 변경인가
--     T1 은 어르신 안전에 관한 관찰 기록이다. 지우면 "언제 무엇을 감지했는지"를
--     되짚을 근거가 사라지고, 시연 후 심사위원 질문("그건 실제로 남나요?")에
--     답할 것이 없어진다. 카드의 필터는 status='ACTIVE' 하나이므로 상태만
--     바꾸면 화면에서는 사라지고 행은 남는다.
--
--   COMPLETED 를 쓰는 이유: 이 알림은 취소된 것이 아니라 "확인되어 닫힌" 것이다
--   (CareRecordStatus 자바독 — SUPERSEDED 는 값이 바뀔 때 쓴다).
--
--   T2/T3 까지 같이 닫는다. 활동 피드가 5건으로 잘리기 때문에, 남은 일일 요약
--   행들이 시연 중 새로 도착한 T1 을 목록 밖으로 밀어낼 수 있다.
UPDATE care_record
   SET status = 'COMPLETED'
 WHERE record_type = 'GUARDIAN_ALERT'
   AND status = 'ACTIVE';

COMMIT;

-- (선택) 같은 웨이크워드 eventId 를 재사용해 재시험하려면 영수증도 지운다.
--   같은 eventId 는 WakeWordCallOrchestrator 가 멱등 처리로 조용히 무시하기 때문.
-- DELETE FROM wake_word_trigger_receipt WHERE event_id = '<재사용할 eventId>';
