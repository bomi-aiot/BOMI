package com.ssafy.bomi.guardian;

import com.ssafy.bomi.guardian.dto.GuardianWalkRequest;
import com.ssafy.bomi.guardian.dto.GuardianWalkResponse;
import com.ssafy.bomi.scenario.application.WalkOrchestrator;
import com.ssafy.bomi.scenario.application.WalkRequestResult;
import com.ssafy.bomi.scenario.domain.WalkRequestDisposition;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Guardian REST adapter; MQTT is never exposed to the browser. */
@RestController
@RequestMapping("/api/v1/guardian/walk-requests")
@Tag(name = "Guardian Walk", description = "산책 시작·종료 요청 — 가디언웹이 호출합니다.")
public class GuardianWalkRequestController {

    private final WalkOrchestrator orchestrator;

    public GuardianWalkRequestController(WalkOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @PostMapping
    @ApiResponses({
        @ApiResponse(responseCode = "202", description = "산책 시작·종료 요청 수락",
            content = @Content(schema = @Schema(implementation = GuardianWalkResponse.class))),
        @ApiResponse(responseCode = "200", description = "종료할 활성 산책 없음",
            content = @Content(schema = @Schema(implementation = GuardianWalkResponse.class))),
        @ApiResponse(responseCode = "400", description = "요청 필드 검증 실패"),
        @ApiResponse(responseCode = "404", description = "미등록 Robot",
            content = @Content(schema = @Schema(implementation = GuardianWalkResponse.class))),
        @ApiResponse(responseCode = "409", description = "산책 정책 거절 또는 requestId 재사용",
            content = @Content(schema = @Schema(implementation = GuardianWalkResponse.class))),
        @ApiResponse(responseCode = "503", description = "MQTT 발행 경계 사용 불가",
            content = @Content(schema = @Schema(implementation = GuardianWalkResponse.class)))
    })
    public ResponseEntity<GuardianWalkResponse> request(
        @Valid @RequestBody GuardianWalkRequest request
    ) {
        WalkRequestResult result = orchestrator.handleGuardianRequest(
            request.requestId(), request.robotId(), request.action());
        return ResponseEntity.status(statusOf(result)).body(GuardianWalkResponse.from(result));
    }

    private static HttpStatus statusOf(WalkRequestResult result) {
        if (result.accepted()) {
            return HttpStatus.ACCEPTED;
        }
        if (result.disposition() == WalkRequestDisposition.REJECTED_NO_ACTIVE_WALK) {
            return HttpStatus.OK;
        }
        if (result.disposition() == WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT) {
            return HttpStatus.NOT_FOUND;
        }
        if (result.disposition() == WalkRequestDisposition.REJECTED_MQTT_UNAVAILABLE) {
            return HttpStatus.SERVICE_UNAVAILABLE;
        }
        return HttpStatus.CONFLICT;
    }
}
