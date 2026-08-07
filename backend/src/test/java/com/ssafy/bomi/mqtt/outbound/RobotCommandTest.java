package com.ssafy.bomi.mqtt.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class RobotCommandTest {

    @Test
    void keepsOpaqueCommandIdAndCopiesPayload() {
        Map<String, Object> payload = new java.util.HashMap<>();
        payload.put("target", "ENTRANCE");

        RobotCommand command = new RobotCommand(
            "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
            UUID.randomUUID(),
            "robot-01",
            RobotCommandType.NAVIGATE,
            OffsetDateTime.parse("2026-07-21T10:30:01+09:00"),
            OffsetDateTime.parse("2026-07-21T10:31:01+09:00"),
            payload
        );
        payload.put("target", "MUTATED");

        assertThat(command.commandId()).isEqualTo("01K0M4Y8B7F5M2N1Q9R6S3T8VX");
        assertThat(command.payload()).containsExactly(Map.entry("target", "ENTRANCE"));
    }

    @Test
    void navigateAcceptsOnlyFinalLogicalTargets() {
        for (String target : new String[] {"LIVING_ROOM", "ENTRANCE", "DEFAULT"}) {
            assertThat(command(RobotCommandType.NAVIGATE, Map.of("target", target))
                .payload()).containsExactly(Map.entry("target", target));
        }
    }

    @Test
    void navigateRejectsMissingLegacyUnknownAndAdditionalPayloadFields() {
        for (Map<String, Object> payload : List.<Map<String, Object>>of(
            Map.of(),
            Map.of("waypointId", "ENTRANCE"),
            Map.of("target", "DEFAULT_POSITION"),
            Map.of("target", "ENTRANCE", "speed", "SLOW"),
            Map.of("target", 1)
        )) {
            assertThatThrownBy(() -> command(RobotCommandType.NAVIGATE, payload))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("NAVIGATE");
        }
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
            Map.of("target", "ENTRANCE")
        ))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("expiresAt");
    }

    @Test
    void followCommandsRequireAnExactlyEmptyPayload() {
        OffsetDateTime occurredAt =
            OffsetDateTime.parse("2026-08-05T16:00:01+09:00");

        for (RobotCommandType type : new RobotCommandType[] {
            RobotCommandType.FOLLOW_START,
            RobotCommandType.FOLLOW_STOP
        }) {
            RobotCommand command = new RobotCommand(
                "command-" + type.name().toLowerCase(),
                UUID.randomUUID(),
                "robot-01",
                type,
                occurredAt,
                occurredAt.plusSeconds(10),
                Map.of());

            assertThat(command.payload()).isEmpty();
            assertThatThrownBy(() -> new RobotCommand(
                "invalid-command-" + type.name().toLowerCase(),
                UUID.randomUUID(),
                "robot-01",
                type,
                occurredAt,
                occurredAt.plusSeconds(10),
                Map.of("trackId", "must-not-be-sent")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("payload");
        }
    }

    @Test
    void cancelRequiresTargetCommandAndReasonCode() {
        RobotCommand command = command(RobotCommandType.CANCEL, Map.of(
            "targetCommandId", "navigate-01",
            "reasonCode", "OPERATOR_CANCELLED"));

        assertThat(command.payload()).containsExactlyInAnyOrderEntriesOf(Map.of(
            "targetCommandId", "navigate-01",
            "reasonCode", "OPERATOR_CANCELLED"));

        assertThatThrownBy(() -> command(RobotCommandType.CANCEL, Map.of()))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("CANCEL");
        assertThatThrownBy(() -> command(RobotCommandType.CANCEL, Map.of(
            "targetCommandId", "navigate-01", "reasonCode", "OPERATOR_CANCELLED",
            "extra", true)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("CANCEL");
    }

    private static RobotCommand command(
        RobotCommandType type,
        Map<String, Object> payload
    ) {
        OffsetDateTime occurredAt =
            OffsetDateTime.parse("2026-08-05T16:00:01+09:00");
        return new RobotCommand(
            "command-" + type.name().toLowerCase(),
            UUID.randomUUID(),
            "robot-01",
            type,
            occurredAt,
            occurredAt.plusSeconds(10),
            payload);
    }
}
