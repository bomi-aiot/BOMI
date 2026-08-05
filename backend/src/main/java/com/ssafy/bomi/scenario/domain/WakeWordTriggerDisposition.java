package com.ssafy.bomi.scenario.domain;

/** Durable outcome of processing one {@code WAKE_WORD_DETECTED} event. */
public enum WakeWordTriggerDisposition {
    RECEIVED,
    ACCEPTED,
    REJECTED_UNKNOWN_ROBOT,
    REJECTED_INACTIVE_ROBOT,
    REJECTED_UNASSIGNED_ROBOT,
    REJECTED_SAFE_STOP,
    REJECTED_ACTIVE_SCENARIO,
    REJECTED_BUSY_MODE
}
