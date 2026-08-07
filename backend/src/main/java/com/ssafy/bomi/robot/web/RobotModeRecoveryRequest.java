package com.ssafy.bomi.robot.web;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** Operator assertion required before Backend may clear a stale safety mode. */
public record RobotModeRecoveryRequest(
    @NotNull
    @AssertTrue(message = "physicalSafetyConfirmed must be true")
    @Schema(description = "현장에서 실제 로봇의 물리적 안전을 확인했는지 여부", requiredMode = Schema.RequiredMode.REQUIRED)
    Boolean physicalSafetyConfirmed,

    @NotBlank
    @Size(max = 500)
    @Schema(description = "감사 이력에 남길 복구 사유", maxLength = 500, requiredMode = Schema.RequiredMode.REQUIRED)
    String reason
) {
}
