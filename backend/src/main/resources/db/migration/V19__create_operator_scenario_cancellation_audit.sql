CREATE TABLE operator_scenario_cancellation_audit (
    id uuid PRIMARY KEY,
    robot_id uuid NOT NULL,
    robot_device_id varchar(64) NOT NULL,
    scenario_id uuid NOT NULL,
    operator_id varchar(100) NOT NULL,
    previous_scenario_status varchar(50) NOT NULL,
    previous_robot_mode varchar(30) NOT NULL,
    target_navigation_command_id varchar(64) NOT NULL,
    cancel_command_id varchar(64) NOT NULL,
    physical_safety_confirmed boolean NOT NULL,
    reason varchar(500) NOT NULL,
    cancelled_at timestamptz NOT NULL,
    CONSTRAINT ck_operator_scenario_cancel_confirmation CHECK (physical_safety_confirmed),
    CONSTRAINT ck_operator_scenario_cancel_reason
        CHECK (length(btrim(reason)) BETWEEN 1 AND 500),
    CONSTRAINT uq_operator_scenario_cancel_scenario UNIQUE (scenario_id),
    CONSTRAINT uq_operator_scenario_cancel_command UNIQUE (cancel_command_id)
);

CREATE INDEX ix_operator_scenario_cancel_robot_time
    ON operator_scenario_cancellation_audit (robot_id, cancelled_at DESC);

COMMENT ON TABLE operator_scenario_cancellation_audit IS
    'Authenticated operator cancellation of an active navigation scenario.';
