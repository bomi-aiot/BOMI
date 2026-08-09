-- dedupe-schedules.sql — 같은 시각의 일정이 여러 행 쌓인 것을 한 행으로 접는다.
--
-- 왜 존재하는가
--   어르신이 "다음 주 화요일에 병원 간다"를 며칠에 걸쳐 여러 번 말하면 발화마다
--   별개의 fact_candidate 가 생기고, 각각이 별개의 care_record 로 실체화됐다.
--   실제로 시연 DB 에 거의 같은 문장의 APPOINTMENT 행이 9개 있었고, 그것이 문맥
--   조립의 상위 5건(careRecordLimit)을 통째로 차지해 정작 필요한 기록을 밀어냈다.
--
-- 재발은 코드로 막았다 (2026-08-10)
--   FactMaterializer 가 일정을 실체화하기 전에 같은 어르신·같은 시각의 ACTIVE
--   일정이 있는지 보고, 있으면 새 행을 만들지 않고 기존 행을 가리킨다.
--   이 스크립트는 그 수정 '이전에' 이미 쌓인 행을 치우는 용도다. 한 번 돌리고 나면
--   평소에는 아무것도 바꾸지 않는다(아래 확인 질의가 0행이면 정상).
--
-- 무엇을 남기는가
--   같은 (어르신, 유형, 시각) 묶음에서 **가장 먼저 기록된 한 행**을 남긴다.
--   그것이 어르신이 그 약속을 처음 말한 시점이고, 뒤에 온 것들은 같은 말의 반복이다.
--
-- 왜 DELETE 가 아니라 SUPERSEDED 인가
--   reset-demo.sql 의 T1 알림 처리와 같은 이유다. 지우면 "언제 무엇이 들어왔는지"를
--   되짚을 근거가 사라진다. 조회는 status='ACTIVE' 만 보므로(ConversationContextService,
--   CareRecordQueryService, DashboardService) 상태만 바꾸면 화면과 프롬프트에서는
--   사라지고 행은 남는다. SUPERSEDED 는 "다른 것으로 대체됨"이라는 뜻이라 여기 맞다.
--
-- 시각이 없는 일정은 건드리지 않는다
--   occurred_at 이 NULL 인 행끼리 "둘 다 시각 없음"을 근거로 합치면 서로 다른 약속이
--   하나로 사라진다. 중복 하나가 소실 하나보다 낫다 — 코드 쪽 판정과 같은 규칙이다.
--
-- 실행
--   ssh bomi 'docker exec -i bomi-postgres psql -U bomi -d bomi' < scripts/dev/dedupe-schedules.sql

-- 1) 먼저 본다 (이 절만 따로 실행) ------------------------------------------
SELECT senior_id, record_type, occurred_at, count(*) AS 행수,
       min(details->>'content') AS 예시
  FROM care_record
 WHERE record_type IN ('APPOINTMENT', 'PERSONAL_SCHEDULE')
   AND status = 'ACTIVE'
   AND occurred_at IS NOT NULL
 GROUP BY senior_id, record_type, occurred_at
HAVING count(*) > 1
 ORDER BY count(*) DESC;

BEGIN;

-- 2) 묶음마다 가장 먼저 들어온 한 행만 남긴다 --------------------------------
--
--   정렬 기준을 occurred_at 으로 쓸 수 없다 — 그 값이 묶음 키라서 전부 같다.
--   care_record 에는 created_at 이 없으므로 id 순서를 쓴다. UUID 는 시간순이
--   아니지만, 여기서 필요한 것은 "무엇이든 하나를 결정적으로 고르는 것"이다.
--   어느 행을 남기든 내용은 같은 약속이고, 결정적이어야 두 번 돌려도 같은 결과가
--   나온다(멱등).
UPDATE care_record AS duplicate
   SET status = 'SUPERSEDED'
  FROM (
      SELECT id,
             row_number() OVER (
                 PARTITION BY senior_id, record_type, occurred_at
                 ORDER BY id
             ) AS rank
        FROM care_record
       WHERE record_type IN ('APPOINTMENT', 'PERSONAL_SCHEDULE')
         AND status = 'ACTIVE'
         AND occurred_at IS NOT NULL
  ) AS ranked
 WHERE duplicate.id = ranked.id
   AND ranked.rank > 1;

COMMIT;

-- 3) 확인 -------------------------------------------------------------------
--   1) 과 같은 질의다. 0행이어야 한다.
SELECT senior_id, record_type, occurred_at, count(*) AS 남은_중복
  FROM care_record
 WHERE record_type IN ('APPOINTMENT', 'PERSONAL_SCHEDULE')
   AND status = 'ACTIVE'
   AND occurred_at IS NOT NULL
 GROUP BY senior_id, record_type, occurred_at
HAVING count(*) > 1;

SELECT record_type, status, count(*)
  FROM care_record
 WHERE record_type IN ('APPOINTMENT', 'PERSONAL_SCHEDULE')
 GROUP BY 1, 2 ORDER BY 1, 2;
