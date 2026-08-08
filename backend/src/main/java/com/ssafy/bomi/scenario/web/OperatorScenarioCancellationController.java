package com.ssafy.bomi.scenario.web;

import com.ssafy.bomi.config.OperatorChannelAuthFilter;
import com.ssafy.bomi.config.OperatorChannelAuthFilterConfig;
import com.ssafy.bomi.scenario.application.OperatorScenarioCancellationResult;
import com.ssafy.bomi.scenario.application.OperatorScenarioCancellationService;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationDisposition;
import jakarta.validation.Valid;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/operator/robots/{deviceId}/active-scenario-cancellations")
@Tag(name = "Operator Scenario Cancellation")
@SecurityRequirement(name = OperatorChannelAuthFilterConfig.SECURITY_SCHEME_NAME)
public class OperatorScenarioCancellationController {

    private final OperatorScenarioCancellationService service;

    public OperatorScenarioCancellationController(OperatorScenarioCancellationService service) {
        this.service = service;
    }

    @PostMapping
    @Operation(
        summary = "Force-cancel an active scenario",
        description = "Terminates the active Scenario and moves the Robot mode to SAFE_STOP. "
            + "When navigation is active, it also queues a Robot CANCEL command. Use mode "
            + "recovery only after confirming the Robot stopped.")
    public ResponseEntity<OperatorScenarioCancellationResponse> cancel(
        @PathVariable String deviceId,
        @RequestAttribute(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE) String operatorId,
        @Valid @RequestBody OperatorScenarioCancellationRequest request
    ) {
        OperatorScenarioCancellationResult result = service.cancelActiveNavigation(
            deviceId, operatorId, Boolean.TRUE.equals(request.physicalSafetyConfirmed()),
            request.reason());
        return ResponseEntity.status(statusOf(result))
            .body(OperatorScenarioCancellationResponse.from(result));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(Map.of("message", error.getMessage()));
    }

    private static HttpStatus statusOf(OperatorScenarioCancellationResult result) {
        if (result.accepted()) return HttpStatus.OK;
        if (result.disposition()
            == OperatorScenarioCancellationDisposition.REJECTED_UNKNOWN_ROBOT) {
            return HttpStatus.NOT_FOUND;
        }
        if (result.disposition()
            == OperatorScenarioCancellationDisposition.REJECTED_MQTT_UNAVAILABLE) {
            return HttpStatus.SERVICE_UNAVAILABLE;
        }
        return HttpStatus.CONFLICT;
    }
}
