package com.ssafy.bomi.mqtt.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class RobotCommandTest {

    @Test
    void keepsOpaqueCommandIdAndCopiesPayload() {
        Map<String, Object> payload = new java.util.HashMap<>();
        payload.put("waypointId", "ENTRANCE");

        RobotCommand command = new RobotCommand(
            "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
            UUID.randomUUID(),
            "robot-01",
            RobotCommandType.NAVIGATE,
            OffsetDateTime.parse("2026-07-21T10:30:01+09:00"),
            OffsetDateTime.parse("2026-07-21T10:31:01+09:00"),
            payload
        );
        payload.put("waypointId", "MUTATED");

        assertThat(command.commandId()).isEqualTo("01K0M4Y8B7F5M2N1Q9R6S3T8VX");
        assertThat(command.payload()).containsEntry("waypointId", "ENTRANCE");
    }

    @Test
    void rejectsExpiredAtOrBeforeOccurrence() {
        OffsetDateTime occurredAt =
            OffsetDateTime.parse("2026-07-21T10:30:01+09:00");

        assertThatThrownBy(() -> new RobotCommand(
            "command-01",
            UUID.randomUUID(),
            "robot-01",
            RobotCommandType.NAVIGATE,
            occurredAt,
            occurredAt,
            Map.of()
        ))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("expiresAt");
    }
}
