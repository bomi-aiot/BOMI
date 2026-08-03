package com.ssafy.bomi.care.web;

import com.ssafy.bomi.care.application.GuardianAlertService;
import com.ssafy.bomi.care.application.GuardianAlertService.AlertOutcome;
import com.ssafy.bomi.care.domain.NotificationTier;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Robot-facing intake for guardian alerts (S15P11E102-211).
 *
 * <p>This is the destination of the robot's outbound queue. The robot stores before it
 * sends, retries with backoff, and never gives up on T1 — all of that stays on the robot.
 * The server's job is to accept an alert and say plainly whether it will reach anyone.</p>
 */
@RestController
@RequestMapping("/api/v1/robot/guardian-alerts")
@Tag(name = "Robot Guardian Alert", description = "보호자 알림 수신 — 로봇(ai_chat notify)이 호출합니다.")
public class RobotGuardianAlertController {

    private final GuardianAlertService service;

    public RobotGuardianAlertController(GuardianAlertService service) {
        this.service = service;
    }

    /**
     * Accepts one alert.
     *
     * <p>Always 201 when the alert was recorded, even if it will not be delivered.
     * <b>A refusal is not an error.</b> Returning 4xx for "consent not granted" would make
     * the robot retry a decision that will never change, and the robot cannot distinguish
     * that from a transient failure without reading the body anyway.</p>
     */
    @PostMapping
    public ResponseEntity<AlertOutcome> accept(@Valid @RequestBody GuardianAlertRequest request) {
        AlertOutcome outcome = service.accept(
            request.seniorId(),
            request.tier(),
            request.payload() == null ? Map.of() : request.payload());
        return ResponseEntity.status(HttpStatus.CREATED).body(outcome);
    }

    /**
     * One alert from the robot's queue.
     *
     * @param tier T1, T2 or T3. T4 never arrives — it means "never shared", so it has no
     *     queue to sit in (CLAUDE.md §9)
     * @param payload aggregates and reasons. <b>Not the senior's words.</b> The robot does
     *     not send them and the server does not ask for them: a path that carries raw
     *     utterances into a guardian alert is how private talk leaks
     */
    public record GuardianAlertRequest(
        @NotNull UUID seniorId,
        @NotNull NotificationTier tier,
        Map<String, Object> payload) {
    }
}
