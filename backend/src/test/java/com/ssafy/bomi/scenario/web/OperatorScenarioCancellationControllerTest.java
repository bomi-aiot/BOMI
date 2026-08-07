package com.ssafy.bomi.scenario.web;

import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.ssafy.bomi.config.OperatorChannelAuthFilter;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.scenario.application.OperatorScenarioCancellationResult;
import com.ssafy.bomi.scenario.application.OperatorScenarioCancellationService;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationDisposition;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

@ExtendWith(MockitoExtension.class)
class OperatorScenarioCancellationControllerTest {

    private static final String ENDPOINT =
        "/api/v1/operator/robots/bomi-AA001/active-scenario-cancellations";
    @Mock OperatorScenarioCancellationService service;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new OperatorScenarioCancellationController(service)).build();
    }

    @Test
    void cancellationReturnsSafeStopAndCorrelation() throws Exception {
        UUID robotId = UUID.randomUUID();
        UUID scenarioId = UUID.randomUUID();
        when(service.cancelActiveNavigation(
            "bomi-AA001", "operator-a", true, "robot inspected"))
            .thenReturn(new OperatorScenarioCancellationResult(
                OperatorScenarioCancellationDisposition.CANCELLED,
                robotId, "bomi-AA001", scenarioId,
                ScenarioStatus.MOVING_TO_ENTRANCE, ScenarioStatus.CANCELLED,
                RobotMode.SCENARIO_ACTIVE, RobotMode.SAFE_STOP,
                "cancel-01", UUID.randomUUID(),
                OffsetDateTime.parse("2026-08-08T00:00:00Z"), "Cancellation queued"));

        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":true,"reason":"robot inspected"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.disposition").value("CANCELLED"))
            .andExpect(jsonPath("$.currentScenarioStatus").value("CANCELLED"))
            .andExpect(jsonPath("$.currentMode").value("SAFE_STOP"))
            .andExpect(jsonPath("$.cancelCommandId").value("cancel-01"));
    }

    @Test
    void falseSafetyConfirmationIsBadRequest() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":false,"reason":"not inspected"}
                    """))
            .andExpect(status().isBadRequest());

        verify(service, never()).cancelActiveNavigation(
            anyString(), anyString(), anyBoolean(), anyString());
    }
}
