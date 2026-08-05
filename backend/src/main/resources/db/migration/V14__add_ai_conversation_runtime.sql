-- AI 대화 요청을 이동 전에 보존하고, MQTT 시작/종료 이벤트를 DB 행과 연결한다.

-- Flyway V14: persist and correlate scenario-driven AI conversations.
ALTER TABLE scenario
    ADD COLUMN conversation_request jsonb,
    ADD COLUMN active_navigation_command_id varchar(64),
    ADD COLUMN active_navigation_target varchar(30);

ALTER TABLE scenario
    ADD CONSTRAINT ck_scenario_conversation_request_object
    CHECK (conversation_request IS NULL OR jsonb_typeof(conversation_request) = 'object'),
    ADD CONSTRAINT ck_scenario_active_navigation_pair
    CHECK ((active_navigation_command_id IS NULL) = (active_navigation_target IS NULL)),
    ADD CONSTRAINT ck_scenario_active_navigation_target
    CHECK (active_navigation_target IS NULL
        OR active_navigation_target IN ('LIVING_ROOM', 'ENTRANCE', 'DEFAULT')),
    ADD CONSTRAINT uq_scenario_active_navigation_command
    UNIQUE (active_navigation_command_id);

ALTER TABLE conversation
    ADD COLUMN start_command_id varchar(64),
    ADD COLUMN ai_started_at timestamptz,
    ADD COLUMN end_outcome varchar(30),
    ADD COLUMN reason_code varchar(100);

-- 이번 시나리오 계약은 하나의 scenario와 하나의 conversation만 연결한다.
ALTER TABLE conversation
    ADD CONSTRAINT uq_conversation_scenario UNIQUE (scenario_id),
    ADD CONSTRAINT uq_conversation_start_command UNIQUE (start_command_id);

-- 10초 시작 대기와 5분 전체 대화 제한을 매 tick마다 전체 테이블 스캔하지 않게 한다.
CREATE INDEX ix_conversation_pending_ai_start
    ON conversation (started_at)
    WHERE status = 'OPEN' AND start_command_id IS NOT NULL AND ai_started_at IS NULL;

CREATE INDEX ix_conversation_active_ai
    ON conversation (ai_started_at)
    WHERE status = 'OPEN' AND start_command_id IS NOT NULL AND ai_started_at IS NOT NULL;

COMMENT ON COLUMN scenario.conversation_request IS
    '이동 전에 확정한 AI 대화 intent, 첫 문장, triggerContext JSON';
COMMENT ON COLUMN conversation.started_at IS
    '일반 대화 시작 시각 또는 시나리오 START_CONVERSATION 요청 시각';
COMMENT ON COLUMN conversation.ai_started_at IS
    'AI가 CONVERSATION_STARTED로 수락을 확인한 시각';
