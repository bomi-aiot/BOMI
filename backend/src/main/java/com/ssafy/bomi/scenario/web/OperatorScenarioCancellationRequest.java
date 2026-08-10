package com.ssafy.bomi.scenario.web;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record OperatorScenarioCancellationRequest(
    @NotNull @AssertTrue(message = "physicalSafetyConfirmed must be true")
    Boolean physicalSafetyConfirmed,
    @NotBlank @Size(max = 500)
    String reason
) {
}
