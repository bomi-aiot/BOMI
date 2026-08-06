package com.ssafy.bomi.guardian.dto;

import com.ssafy.bomi.scenario.domain.WalkAction;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** Guardian input deliberately excludes source; Backend always assigns APP. */
public record GuardianWalkRequest(
    @NotBlank
    @Size(max = 64)
    String requestId,

    @NotBlank
    @Size(max = 64)
    @Pattern(regexp = "^[A-Za-z0-9._-]+$")
    String robotId,

    @NotNull
    WalkAction action
) {
}
