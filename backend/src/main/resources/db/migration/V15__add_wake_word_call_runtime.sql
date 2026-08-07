-- "보미야" 호출은 AI 대화를 만들지 않고 거실 이동 결과까지만 관리한다.
-- 트리거와 최종 Robot 결과를 재시작 뒤에도 상관시킬 수 있도록 최소 이력을 보존한다.

ALTER TABLE scenario
    ADD COLUMN trigger_context jsonb,
    ADD COLUMN completion_result_code varchar(50),
    ADD COLUMN completion_reason_code varchar(100);

ALTER TABLE scenario
    ADD CONSTRAINT ck_scenario_trigger_context_object
    CHECK (trigger_context IS NULL OR jsonb_typeof(trigger_context) = 'object');

ALTER TABLE scenario
    ADD CONSTRAINT ck_scenario_wake_word_external_event
    CHECK (scenario_type <> 'WAKE_WORD_CALL' OR external_event_id IS NOT NULL);

-- 기존 HOMECOMING/WELLNESS_CHECK는 external_event_id에 센서 ID를 넣은 행이 있으므로
-- 컬럼 전체를 UNIQUE로 만들 수 없다. 호출 타입의 실제 MQTT eventId만 영속 멱등 키로 묶는다.
CREATE UNIQUE INDEX uq_scenario_wake_word_event
    ON scenario (external_event_id)
    WHERE scenario_type = 'WAKE_WORD_CALL' AND external_event_id IS NOT NULL;

-- ScenarioStartGuard의 exists-then-insert는 동시 트랜잭션 둘을 직렬화하지 못한다.
-- 최종 방어선은 DB가 맡아 한 어르신에게 활성 시나리오가 하나만 존재하게 한다.
-- NOT IN을 사용해 향후 새 활성 상태가 추가돼도 자동으로 이 불변식에 포함한다.
CREATE UNIQUE INDEX uq_scenario_one_active_per_senior
    ON scenario (senior_id)
    WHERE final_status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT');

CREATE TABLE wake_word_trigger_receipt (
    event_id varchar(64) PRIMARY KEY,
    robot_device_id varchar(64) NOT NULL,
    occurred_at timestamptz NOT NULL,
    keyword varchar(20) NOT NULL,
    confidence double precision,
    disposition varchar(40) NOT NULL,
    scenario_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_wake_word_trigger_confidence
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT ck_wake_word_trigger_resolution
        CHECK (
            (disposition = 'RECEIVED' AND scenario_id IS NULL)
            OR (disposition = 'ACCEPTED' AND scenario_id IS NOT NULL)
            OR (disposition LIKE 'REJECTED_%' AND scenario_id IS NULL)
        )
);

COMMENT ON COLUMN scenario.trigger_context IS
    '시나리오 최초 트리거의 최소 구조화 문맥. 원본 음성/전체 STT는 저장하지 않는다.';
COMMENT ON COLUMN scenario.completion_result_code IS
    '시나리오를 끝낸 Robot 명령의 안정적인 resultCode.';
COMMENT ON COLUMN scenario.completion_reason_code IS
    '실패·취소·시간초과의 안정적인 reasonCode. 사람용 자유 문장은 저장하지 않는다.';
