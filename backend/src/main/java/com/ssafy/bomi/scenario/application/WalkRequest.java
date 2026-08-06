package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestIngress;
import com.ssafy.bomi.scenario.domain.WalkRequestSource;
import java.time.OffsetDateTime;
import java.util.UUID;

/** Transport-neutral command consumed by the single walk application service. */
public record WalkRequest(
    WalkRequestIngress ingress,
    String requestId,
    String robotDeviceId,
    WalkAction action,
    WalkRequestSource source,
    UUID conversationId,
    OffsetDateTime occurredAt
) {
    public WalkRequest {
        if (ingress == null) {
            throw new IllegalArgumentException("ingress must not be null");
        }
        requestId = requireText(requestId, "requestId", 64);
        robotDeviceId = requireText(robotDeviceId, "robotDeviceId", 64);
        if (action == null) {
            throw new IllegalArgumentException("action must not be null");
        }
        if (source == null) {
            throw new IllegalArgumentException("source must not be null");
        }
        if (occurredAt == null) {
            throw new IllegalArgumentException("occurredAt must not be null");
        }
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " must not exceed " + maxLength + " characters");
        }
        return value;
    }
}
