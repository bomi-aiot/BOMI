package com.ssafy.bomi.robot.web;

import com.ssafy.bomi.config.OperatorChannelAuthFilterConfig;
import com.ssafy.bomi.robot.application.OperatorRobotNotFoundException;
import com.ssafy.bomi.robot.application.OperatorRobotRuntimeQueryService;
import com.ssafy.bomi.robot.application.OperatorRobotRuntimeState;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/operator/robots/{deviceId}/runtime-state")
@Tag(name = "Operator Robot Runtime")
@SecurityRequirement(name = OperatorChannelAuthFilterConfig.SECURITY_SCHEME_NAME)
public class OperatorRobotRuntimeController {

    private final OperatorRobotRuntimeQueryService service;

    public OperatorRobotRuntimeController(OperatorRobotRuntimeQueryService service) {
        this.service = service;
    }

    @GetMapping
    @Operation(summary = "Read Robot mode and active Scenario state")
    public OperatorRobotRuntimeState get(@PathVariable String deviceId) {
        return service.get(deviceId);
    }

    @ExceptionHandler(OperatorRobotNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(OperatorRobotNotFoundException error) {
        return ResponseEntity.status(404).body(Map.of("message", error.getMessage()));
    }
}
