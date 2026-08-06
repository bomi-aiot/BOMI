package com.ssafy.bomi.scenario.domain;

/** Durable decision for one WALK_REQUESTED/Guardian request id. */
public enum WalkRequestDisposition {
    RECEIVED(false, null),
    ACCEPTED(true, null),
    NO_OP_ALREADY_STOPPING(true, "ALREADY_STOPPING"),
    REJECTED_NO_ACTIVE_WALK(false, "NO_ACTIVE_WALK"),
    REJECTED_UNKNOWN_ROBOT(false, "UNKNOWN_ROBOT"),
    REJECTED_INACTIVE_ROBOT(false, "INACTIVE_ROBOT"),
    REJECTED_UNASSIGNED_ROBOT(false, "UNASSIGNED_ROBOT"),
    REJECTED_SAFE_STOP(false, "SAFE_STOP"),
    REJECTED_REST_GUARD(false, "REST_GUARD"),
    REJECTED_ACTIVE_SCENARIO(false, "ACTIVE_SCENARIO"),
    REJECTED_BUSY_MODE(false, "BUSY_MODE"),
    REJECTED_REQUEST_ID_REUSED(false, "REQUEST_ID_REUSED"),
    REJECTED_MQTT_UNAVAILABLE(false, "MQTT_UNAVAILABLE");

    private final boolean accepted;
    private final String reasonCode;

    WalkRequestDisposition(boolean accepted, String reasonCode) {
        this.accepted = accepted;
        this.reasonCode = reasonCode;
    }

    public boolean isAccepted() {
        return accepted;
    }

    public String reasonCode() {
        return reasonCode;
    }
}
