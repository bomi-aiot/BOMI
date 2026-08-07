package com.ssafy.bomi.robot.domain;

/** Application outcome; only the two accepted values are written to the audit table. */
public enum RobotModeRecoveryDisposition {
    RECOVERED,
    NO_OP_ALREADY_IDLE,
    REJECTED_UNKNOWN_ROBOT,
    REJECTED_INACTIVE_ROBOT,
    REJECTED_UNASSIGNED_ROBOT,
    REJECTED_SENIOR_NOT_FOUND,
    REJECTED_ASSIGNMENT_CHANGED,
    REJECTED_ACTIVE_SCENARIO,
    REJECTED_MODE_NOT_RECOVERABLE;

    public boolean accepted() {
        return this == RECOVERED || this == NO_OP_ALREADY_IDLE;
    }
}
