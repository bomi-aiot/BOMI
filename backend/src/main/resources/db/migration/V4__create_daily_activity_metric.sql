-- V4 : 일간 활동 지표(daily_activity_metric)
--
-- T2 일일 요약이 시계열로 읽는 표다. 보호자에게는 집계와 이상치만 보낸다.
-- 원본 이동 기록이나 대화 기록을 보내지 않는다(CLAUDE.md §9, §11 프라이버시).
--
-- 왜 care_record 관찰 타입이 아니라 별도 표인가
--   care_record 는 '사건 하나'를 적는 곳이고 details 가 jsonb 다. T2 는 "지난 14일 수면
--   추세"처럼 열 단위 시계열 질의를 한다. jsonb 에서 매번 추출·형변환하면 추세 질의가
--   전부 풀스캔이 된다. 하루 1행 집계는 성격이 다르므로 표를 나눈다.
--
-- 주기 측정값을 전부 저장하지 않는다
--   ERD 의 "관찰을 다 적지 않는다" 원칙과 같다. 하루 1행 집계만 남긴다. microSD 수명과도
--   직결된다(§18).
--
-- 참고: CLAUDE.md §9(티어), §19(DB 작업 항목)
CREATE TABLE daily_activity_metric (
    id                         uuid          NOT NULL,
    senior_id                  uuid          NOT NULL,

    -- 어르신의 '로컬' 날짜다. app_user.time_zone 으로 계산한다.
    -- UTC 로 계산하면 자정 근처 활동이 엉뚱한 날로 넘어가고, 그러면 추세가 틀어진다.
    metric_date                date          NOT NULL,

    -- ── 지표: 전부 NULL 허용 ──────────────────────────────────────────────
    --
    -- 이게 이 표에서 가장 중요한 결정이다. **모르는 것과 0은 다르다.**
    -- 수면 시간이 NULL(측정 못 함)인데 0으로 저장하면, T2 추세는 "어제 한숨도 못 잤다"고
    -- 보호자에게 보고한다. 그런 오탐이 쌓이면 보호자가 알림을 읽지 않게 되고,
    -- 그때부터 진짜 응급을 놓친다. 시끄러운 감지기는 짜증이 아니라 안전 실패다.
    -- 따라서 기본값을 두지 않고, 채우지 못한 지표는 NULL 로 남긴다.

    -- 복약 이행: 비율이 아니라 분자·분모를 따로 저장한다.
    --   "4번 중 3번"이라고 말할 수 있어야 하고, 예정이 0인 날의 비율(0/0)을 만들지 않는다.
    medication_taken_count     smallint,
    medication_scheduled_count smallint,

    meal_count                 smallint,
    water_intake_count         smallint,
    sleep_minutes              integer,

    -- 1~5. 대화에서 추정한 값이며 진단이 아니다.
    mood_score                 smallint,

    -- 발화량을 어르신과 로봇으로 나눈다. 합쳐 세면 로봇이 혼자 떠든 날이
    -- '활발한 날'로 집계된다. conversation_message.trigger_type 이 이 분리를 가능하게 한다.
    senior_utterance_count     integer,
    robot_utterance_count      integer,

    -- occupancy_event 에서 집계한다. 발화량 외의 두 번째 활동 지표다.
    outing_count               smallint,

    created_at                 timestamptz   NOT NULL,
    updated_at                 timestamptz   NOT NULL,

    CONSTRAINT pk_daily_activity_metric PRIMARY KEY (id),

    -- 하루에 한 행. 배치가 재실행돼도 행이 늘지 않아야 한다(멱등).
    -- (senior_id, metric_date) 접두사가 "이 어르신의 최근 N일" 질의도 함께 커버하므로
    -- 별도 인덱스를 두지 않는다.
    CONSTRAINT uq_daily_activity_metric_day UNIQUE (senior_id, metric_date)
);
