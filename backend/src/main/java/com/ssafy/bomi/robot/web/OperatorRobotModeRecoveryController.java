package com.ssafy.bomi.robot.web;

import com.ssafy.bomi.config.OperatorChannelAuthFilter;
import com.ssafy.bomi.config.OperatorChannelAuthFilterConfig;
import com.ssafy.bomi.robot.application.RobotModeRecoveryResult;
import com.ssafy.bomi.robot.application.RobotModeRecoveryService;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
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

/** Authenticated operator adapter for database-only mode recovery. */
@RestController
@RequestMapping("/api/v1/operator/robots/{deviceId}/mode-recoveries")
@Tag(
    name = "Operator Robot Recovery",
    description = "인증된 운영 도구가 호출합니다. 실제 E-stop이나 모터 정지를 대신하지 않습니다."
)
@SecurityRequirement(name = OperatorChannelAuthFilterConfig.SECURITY_SCHEME_NAME)
public class OperatorRobotModeRecoveryController {

    private final RobotModeRecoveryService service;

    public OperatorRobotModeRecoveryController(RobotModeRecoveryService service) {
        this.service = service;
    }

    @PostMapping
    @Operation(
        summary = "안전 확인 후 Robot DB mode를 IDLE로 복구",
        description = "활성 Scenario가 없는 SAFE_STOP 또는 비정상 SCENARIO_ACTIVE만 복구합니다. "
            + "MQTT 명령은 발행하지 않습니다. 이미 IDLE이면 감사 이력만 남기는 멱등 no-op입니다."
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "복구 또는 이미 IDLE인 멱등 no-op",
            content = @Content(schema = @Schema(implementation = RobotModeRecoveryResponse.class))),
        @ApiResponse(responseCode = "400", description = "물리 안전 확인 또는 reason 검증 실패"),
        @ApiResponse(responseCode = "401", description = "운영자 공유 비밀 누락 또는 불일치"),
        @ApiResponse(responseCode = "404", description = "미등록 Robot"),
        @ApiResponse(responseCode = "409", description = "활성 Scenario 또는 복구 불가능한 Robot 상태"),
        @ApiResponse(responseCode = "503", description = "서버 운영자 인증 설정 누락")
    })
    public ResponseEntity<RobotModeRecoveryResponse> recover(
        @PathVariable String deviceId,
        @RequestAttribute(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE) String operatorId,
        @Valid @RequestBody RobotModeRecoveryRequest request
    ) {
        RobotModeRecoveryResult result = service.recoverToIdle(
            deviceId,
            operatorId,
            Boolean.TRUE.equals(request.physicalSafetyConfirmed()),
            request.reason());
        return ResponseEntity.status(statusOf(result)).body(RobotModeRecoveryResponse.from(result));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(Map.of("message", error.getMessage()));
    }

    private static HttpStatus statusOf(RobotModeRecoveryResult result) {
        if (result.accepted()) {
            return HttpStatus.OK;
        }
        if (result.disposition() == RobotModeRecoveryDisposition.REJECTED_UNKNOWN_ROBOT) {
            return HttpStatus.NOT_FOUND;
        }
        return HttpStatus.CONFLICT;
    }
}
