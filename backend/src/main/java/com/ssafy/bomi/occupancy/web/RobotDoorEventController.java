package com.ssafy.bomi.occupancy.web;

import com.ssafy.bomi.occupancy.application.DoorEventService;
import com.ssafy.bomi.occupancy.application.DoorEventService.DoorEventOutcome;
import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver.Signal;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Where the robot's forwarded entrance events land (S15P11E102-226).
 *
 * <p><b>The robot has been calling this since 208 and getting a 404.</b> It handled that
 * gracefully — a failed forward logs a warning and the local safety watch carries on — but
 * it meant the backend never saw a door event, so direction was never resolved and no
 * greeting has ever been spoken.</p>
 *
 * <p>The path matches what {@code backend_client/door_client.py} already posts to.</p>
 */
@RestController
@RequestMapping("/api/v1/seniors/{seniorId}/door-events")
@Tag(
        name = "Robot Door Event",
        description = "현관 이벤트 전달 — 로봇(ai_chat door_client)이 호출합니다.")
public class RobotDoorEventController {

    private static final Logger log = LoggerFactory.getLogger(RobotDoorEventController.class);

    private final DoorEventService service;

    public RobotDoorEventController(DoorEventService service) {
        this.service = service;
    }

    /**
     * Accepts one entrance signal and answers with what to do about it.
     *
     * <p>Types the robot may send are the ones in its own contract
     * ({@code contracts/door.py}). {@code DOOR_CLOSED} and {@code HEARTBEAT} say nothing
     * about direction, so they are accepted and ignored here rather than rejected — the
     * robot uses them locally, and a 4xx would make it look like a contract mismatch.</p>
     */
    @PostMapping
    public ResponseEntity<DoorEventResponse> accept(
        @PathVariable UUID seniorId,
        @Valid @RequestBody DoorEventRequest request) {

        Signal signal = switch (request.type()) {
            case "DOOR_OPENED" -> Signal.DOOR_OPENED;
            case "MOTION_DETECTED" -> Signal.MOTION;
            default -> null;
        };

        if (signal == null) {
            log.debug("entrance event {} carries no direction information; ignoring",
                request.type());
            return ResponseEntity.ok(DoorEventResponse.ignored());
        }

        DoorEventOutcome outcome = service.accept(
            seniorId, signal, toTime(request.receivedAt()), toTime(request.reportedAt()));

        return ResponseEntity.ok(new DoorEventResponse(
            outcome.resolved(),
            outcome.direction() == null ? null : outcome.direction().name(),
            outcome.occupancy() == null ? null : outcome.occupancy().name(),
            outcome.greeting()));
    }

    /**
     * Epoch seconds to a time we can compare.
     *
     * <p>Null stays null: {@code reportedAt} is the Pi's own claim and is genuinely absent
     * when the firmware does not send one. Substituting "now" would hide a broken RTC by
     * making every clock look correct.</p>
     */
    private static OffsetDateTime toTime(Double epochSeconds) {
        if (epochSeconds == null) {
            return null;
        }
        long seconds = (long) Math.floor(epochSeconds);
        long nanos = Math.round((epochSeconds - seconds) * 1_000_000_000L);
        return OffsetDateTime.ofInstant(Instant.ofEpochSecond(seconds, nanos), ZoneOffset.UTC);
    }

    /**
     * One entrance signal, in the shape {@code door_client.py} already sends.
     *
     * @param receivedAt <b>the authoritative time</b> — when the Jetson received it. A
     *     Raspberry Pi without a battery-backed RTC can boot years off, and a wrong ordering
     *     here inverts the direction (CLAUDE.md §11)
     * @param reportedAt the Pi's own claim. Recorded so a broken clock is visible, never
     *     used for ordering
     * @param direction whatever the sensor topic claimed. <b>Ignored.</b> Direction is this
     *     server's job; trusting a firmware-derived value would put the judgement in two
     *     places
     */
    public record DoorEventRequest(
        String eventId,
        @NotBlank String type,
        String sourceId,
        Double receivedAt,
        Double reportedAt,
        String direction,
        Map<String, Object> payload) {
    }

    /**
     * What the robot should do.
     *
     * @param resolved false while the passage is still incomplete — one sensor fired and we
     *     are waiting for the other
     * @param occupancy the confirmed value to apply, or null to leave the robot's
     *     conservative UNKNOWN alone
     * @param greeting the single sentence to speak, or null to stay quiet
     */
    public record DoorEventResponse(boolean resolved, String direction, String occupancy,
        String greeting) {

        static DoorEventResponse ignored() {
            return new DoorEventResponse(false, null, null, null);
        }
    }
}
