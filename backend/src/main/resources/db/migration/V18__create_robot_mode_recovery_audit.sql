-- Operator mode recovery is a database-only safety operation. It never represents an E-stop,
-- motor stop, navigation cancellation, or any MQTT command.
CREATE TABLE robot_mode_recovery_audit (
    id uuid PRIMARY KEY,
    robot_id uuid NOT NULL,
    robot_device_id varchar(64) NOT NULL,
    operator_id varchar(100) NOT NULL,
    previous_mode varchar(30) NOT NULL,
    target_mode varchar(30) NOT NULL,
    disposition varchar(30) NOT NULL,
    physical_safety_confirmed boolean NOT NULL,
    reason varchar(500) NOT NULL,
    recovered_at timestamptz NOT NULL,
    CONSTRAINT ck_robot_mode_recovery_device_id
        CHECK (length(btrim(robot_device_id)) BETWEEN 1 AND 64),
    CONSTRAINT ck_robot_mode_recovery_operator_id
        CHECK (length(btrim(operator_id)) BETWEEN 1 AND 100),
    CONSTRAINT ck_robot_mode_recovery_reason
        CHECK (length(btrim(reason)) BETWEEN 1 AND 500),
    CONSTRAINT ck_robot_mode_recovery_target_idle
        CHECK (target_mode = 'IDLE'),
    CONSTRAINT ck_robot_mode_recovery_physical_confirmation
        CHECK (physical_safety_confirmed),
    CONSTRAINT ck_robot_mode_recovery_disposition
        CHECK (
            (disposition = 'RECOVERED'
                AND previous_mode IN ('SAFE_STOP', 'SCENARIO_ACTIVE'))
            OR (disposition = 'NO_OP_ALREADY_IDLE' AND previous_mode = 'IDLE')
        )
);

CREATE INDEX ix_robot_mode_recovery_audit_robot_time
    ON robot_mode_recovery_audit (robot_id, recovered_at DESC);

COMMENT ON TABLE robot_mode_recovery_audit IS
    'Authenticated operator audit for DB mode recovery to IDLE; never a physical safety action.';
COMMENT ON COLUMN robot_mode_recovery_audit.operator_id IS
    'Server-configured authenticated operator identity, never supplied in the request body.';
COMMENT ON COLUMN robot_mode_recovery_audit.recovered_at IS
    'Backend time at which recovery or the already-IDLE no-op was committed.';
