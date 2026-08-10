package com.ssafy.bomi.scenario.domain;

public enum OperatorScenarioCancellationDisposition {
    CANCELLED(true),
    NO_OP_NO_ACTIVE_SCENARIO(true),
    REJECTED_UNKNOWN_ROBOT(false),
    REJECTED_INACTIVE_ROBOT(false),
    REJECTED_UNASSIGNED_ROBOT(false),
    REJECTED_SENIOR_NOT_FOUND(false),
    REJECTED_ASSIGNMENT_CHANGED(false),
    REJECTED_MULTIPLE_ACTIVE_SCENARIOS(false),
    REJECTED_NO_ACTIVE_NAVIGATION(false),
    REJECTED_MQTT_UNAVAILABLE(false);

    private final boolean accepted;

    OperatorScenarioCancellationDisposition(boolean accepted) {
        this.accepted = accepted;
    }

    public boolean accepted() {
        return accepted;
    }
}
