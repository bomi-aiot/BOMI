-- 산책은 한 Scenario 안에서 FOLLOW_START와 FOLLOW_STOP을 별도 상관관계로 관리한다.
-- Voice MQTT와 Guardian REST 요청은 같은 영속 receipt/상태 머신을 사용한다.

ALTER TABLE scenario
    ADD COLUMN follow_start_command_id varchar(64),
    ADD COLUMN follow_stop_command_id varchar(64),
    ADD COLUMN follow_start_requested_at timestamptz,
    ADD COLUMN following_started_at timestamptz,
    ADD COLUMN follow_stop_requested_at timestamptz,
    ADD COLUMN last_follow_result_event_id varchar(64),
    ADD COLUMN last_follow_command_id varchar(64),
    ADD COLUMN last_follow_result_code varchar(50),
    ADD COLUMN last_follow_reason_code varchar(100),
    ADD COLUMN last_follow_result_at timestamptz;

ALTER TABLE scenario
    ADD CONSTRAINT ck_scenario_walk_start_correlation
        CHECK (
            scenario_type <> 'WALK'
            OR (
                external_event_id IS NOT NULL
                AND follow_start_command_id IS NOT NULL
                AND follow_start_requested_at IS NOT NULL
            )
        ),
    ADD CONSTRAINT ck_scenario_follow_stop_correlation
        CHECK (
            (follow_stop_command_id IS NULL AND follow_stop_requested_at IS NULL)
            OR (follow_stop_command_id IS NOT NULL AND follow_stop_requested_at IS NOT NULL)
        ),
    ADD CONSTRAINT ck_scenario_follow_command_ids_differ
        CHECK (
            follow_stop_command_id IS NULL
            OR follow_start_command_id IS NULL
            OR follow_stop_command_id <> follow_start_command_id
        );

CREATE INDEX ix_scenario_active_walk_robot
    ON scenario (robot_id)
    WHERE scenario_type = 'WALK'
      AND final_status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT');

CREATE TABLE walk_request_receipt (
    id uuid PRIMARY KEY,
    ingress varchar(30) NOT NULL,
    request_id varchar(64) NOT NULL,
    robot_device_id varchar(64) NOT NULL,
    action varchar(10) NOT NULL,
    source varchar(10) NOT NULL,
    conversation_id uuid,
    occurred_at timestamptz NOT NULL,
    disposition varchar(50) NOT NULL,
    scenario_id uuid,
    scenario_status varchar(50),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_walk_request_ingress_request UNIQUE (ingress, request_id),
    CONSTRAINT ck_walk_request_ingress
        CHECK (ingress IN ('MQTT', 'GUARDIAN_REST')),
    CONSTRAINT ck_walk_request_action
        CHECK (action IN ('START', 'STOP')),
    CONSTRAINT ck_walk_request_source
        CHECK (source IN ('VOICE', 'APP')),
    CONSTRAINT ck_walk_request_resolution
        CHECK (
            (disposition = 'RECEIVED' AND scenario_id IS NULL AND scenario_status IS NULL)
            OR (
                disposition IN ('ACCEPTED', 'NO_OP_ALREADY_STOPPING')
                AND scenario_id IS NOT NULL
                AND scenario_status IS NOT NULL
            )
            OR (
                disposition LIKE 'REJECTED_%'
                AND scenario_id IS NULL
                AND scenario_status IS NULL
            )
        )
);

COMMENT ON COLUMN scenario.follow_start_command_id IS
    '산책 FOLLOW_START commandId. STARTED 뒤에도 자체 종료 상관관계를 위해 보존한다.';
COMMENT ON COLUMN scenario.follow_stop_command_id IS
    '산책 FOLLOW_STOP commandId. FOLLOW_START와 별개의 명령 식별자다.';
COMMENT ON TABLE walk_request_receipt IS
    'Voice MQTT eventId와 Guardian REST requestId의 수락·거절을 재시작 뒤에도 재생하는 멱등 장부.';
