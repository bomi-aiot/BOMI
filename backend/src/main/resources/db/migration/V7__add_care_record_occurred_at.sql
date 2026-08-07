-- V7 : care_record 에 발생 시각(occurred_at) 추가 (S15P11E102-230)
--
-- 무엇이 문제였나
--   care_record 에 시각 컬럼이 하나도 없었다. created_at 도, occurred_at 도 없다.
--   '언제 일어난 일인가'가 details jsonb 안에 규약으로만 들어 있었고, 규약이 이미
--   네 개였다.
--
--     details.scheduledAt  ISO 문자열   MEDICATION_TAKEN 이 매칭된 복약 슬롯 (224)
--     details.startsAt     ISO 문자열   일정/약속의 시작 시각 (221)
--     details.ts           epoch 초     로봇이 올린 GUARDIAN_ALERT (211)
--     details.metricDate   ISO 날짜     일일 요약이 올린 GUARDIAN_ALERT (211)
--
-- 왜 고치는가
--   1. 시계열 질의를 SQL 로 할 수 없었다. "지난 14일 복약 추세"를 물으면 그 어르신의
--      돌봄기록을 '전부' 로드해서 자바에서 JSON 을 파싱하는 수밖에 없었다. 일간 배치를
--      스케줄하는 순간 매일 전체 스캔이 되고, 기록이 쌓일수록 나빠진다.
--      V4 가 별도 표를 만든 이유("jsonb 에서 매번 추출·형변환하면 추세 질의가 전부
--      풀스캔이 된다")와 정확히 같은 문제가 원본 표에 남아 있었다.
--
--   2. 키를 빠뜨린 쓰기가 조용히 사라졌다. details 의 키는 스키마가 강제하지 않는다.
--      새 쓰기 경로가 그 키를 안 넣어도 컴파일도 저장도 통과하고, 집계에서만 빠진다.
--      보호자는 있지도 않은 복약 누락을 보게 된다.
--      ★ 실제로 이 일이 이미 일어나 있었다. GreetingDecider.todaysAppointment 는
--        일정 기록에서 scheduledAt 을 읽는데, 일정을 쓰는 쪽은 startsAt 을 넣는다.
--        그래서 현관에서 "오늘 약속" 인사가 한 번도 나간 적이 없다. 이 마이그레이션이
--        두 규약을 한 컬럼으로 합치면서 함께 고쳐진다.
--
--   3. 관찰 기록에는 시각이 아예 없었다. REST_OBSERVATION 은 details 에 상태만 있고
--      언제 관찰했는지가 없다. "어제 몇 시부터 주무셨나"를 물을 방법이 없었다.
--
-- occurred_at 의 의미  ★ 여기서 한 가지로 정한다
--   '이 기록이 시간축 위에서 놓이는 지점'이다. 일어난 일이면 일어난 시각, 예정된
--   일이면 예정 시각. 축을 하나로 두어야 범위 질의가 성립한다.
--
--     MEDICATION_TAKEN        매칭된 복약 슬롯 시각 (details.scheduledAt)
--                             실제 대답한 순간은 details.respondedAt 에 그대로 둔다.
--                             집계가 묻는 것은 "그 약이 몇 시 약이었나"이지
--                             "몇 초에 대답했나"가 아니다.
--     APPOINTMENT/일정        시작 시각 (details.startsAt)
--     GUARDIAN_ALERT          알림이 발생한 시각
--     *_OBSERVATION           관찰한 시각
--     MEDICATION              NULL. 처방 자체는 시점이 아니다.
--     MEDICATION_SCHEDULE     NULL. 반복 규칙이라 시간축의 한 점이 아니다.
--                             (반복 전개는 recurrence 가 담당한다)
--
-- 왜 NOT NULL 로 만들지 않는가
--   기존 행 중에는 진짜로 시각을 알 수 없는 것이 있고, 그것을 지어내면 안 된다.
--   0 이나 마이그레이션 시각으로 채우면 보호자 화면에서 오래된 알림이 오늘 맨 위에
--   뜬다. 모르는 것은 NULL 로 남긴다 — V4 의 "모르는 것과 0 은 다르다"와 같은 원칙이다.
--   반복 규칙(MEDICATION_SCHEDULE)처럼 '원래 없는' 경우도 있어서, NOT NULL 은 애초에
--   맞지 않는다.
--
-- 참고: CLAUDE.md §19(DB 작업 항목) / V1__init.sql(care_record) /
--       V4__create_daily_activity_metric.sql(같은 이유로 별도 표를 만든 주석)

ALTER TABLE care_record
    ADD COLUMN occurred_at timestamptz;

COMMENT ON COLUMN care_record.occurred_at IS
    '이 기록이 시간축 위에 놓이는 지점. 일어난 일이면 일어난 시각, 예정된 일이면 예정 시각. '
    'NULL 은 "모른다" 또는 "시점이 없다(반복 규칙, 처방 자체)"를 뜻한다. S15P11E102-230';


-- ── 백필 ─────────────────────────────────────────────────────────────────────
--
-- 지금이 가장 싸다. 기록이 적을 때 옮긴다.
--
-- 왜 함수를 만들어 쓰는가
--   details 는 jsonb 이고 값의 형식을 아무도 강제하지 않았다. 깨진 문자열이 한 줄만
--   있어도 캐스팅이 예외를 던지고 '마이그레이션 전체가' 실패한다. 정규식으로 걸러도
--   '2026-13-45T00:00:00Z' 같은 것은 통과한 뒤 캐스팅에서 죽는다.
--   그래서 예외를 삼키고 NULL 을 돌려주는 함수로 감싼다. 읽을 수 없는 값은 NULL 로
--   남기는 것이 이 마이그레이션의 의도된 결과다 — 지어내지 않는다.
--
-- 함수는 이 마이그레이션 안에서만 살고 끝에서 지운다. 남겨두면 다음 사람이 이것이
-- 정식 유틸리티인 줄 알고 쓰기 시작한다.

CREATE FUNCTION bomi_v7_try_timestamptz(raw text) RETURNS timestamptz AS $$
BEGIN
    RETURN raw::timestamptz;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION bomi_v7_try_epoch(raw text) RETURNS timestamptz AS $$
BEGIN
    RETURN to_timestamp(raw::double precision);
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION bomi_v7_try_local_date(raw text) RETURNS timestamptz AS $$
BEGIN
    -- metricDate 는 '어르신의 로컬 날짜'다(V4 참고). 그 날의 시작으로 놓는다.
    -- UTC 자정으로 두면 한국 어르신의 요약이 전날 09:00 로 표시된다.
    RETURN (raw::date)::timestamp AT TIME ZONE 'Asia/Seoul';
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- COALESCE 순서 = 구체적인 규약이 먼저.
-- 한 행이 두 키를 동시에 갖는 경우는 없지만, 순서를 명시해 두면 나중에 그런 행이
-- 생겨도 어느 쪽이 이기는지 읽는 사람이 알 수 있다.
UPDATE care_record
SET occurred_at = COALESCE(
        bomi_v7_try_timestamptz(details ->> 'scheduledAt'),
        bomi_v7_try_timestamptz(details ->> 'startsAt'),
        bomi_v7_try_epoch(details ->> 'ts'),
        bomi_v7_try_local_date(details ->> 'metricDate'))
WHERE occurred_at IS NULL
  AND details ?| ARRAY['scheduledAt', 'startsAt', 'ts', 'metricDate'];

DROP FUNCTION bomi_v7_try_timestamptz(text);
DROP FUNCTION bomi_v7_try_epoch(text);
DROP FUNCTION bomi_v7_try_local_date(text);


-- ── 인덱스 ───────────────────────────────────────────────────────────────────
--
-- 컬럼 순서가 곧 질의 순서다. 추세 질의는 항상 이렇게 들어온다.
--
--     WHERE senior_id = ? AND record_type = ? AND occurred_at >= ? AND occurred_at < ?
--
-- senior_id 를 맨 앞에 두는 이유: 어떤 질의든 한 어르신으로 먼저 좁혀진다.
-- occurred_at 을 맨 뒤에 두는 이유: 범위 조건은 마지막 컬럼에서만 인덱스를 탈 수 있다.
--
-- 부분 인덱스(WHERE occurred_at IS NOT NULL)로 만들지 않았다. 크기는 조금 줄지만,
-- (senior_id, record_type) 만으로 조회하는 기존 질의도 이 인덱스를 쓸 수 있어야 한다.
-- 우리 규모에서 몇 킬로바이트를 아끼려고 "왜 인덱스를 안 타지"를 만들 이유가 없다.
CREATE INDEX ix_care_record_senior_type_occurred
    ON care_record (senior_id, record_type, occurred_at);
