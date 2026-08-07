package com.ssafy.bomi.robot.web;

import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.ssafy.bomi.config.OperatorChannelAuthFilter;
import com.ssafy.bomi.robot.application.RobotModeRecoveryResult;
import com.ssafy.bomi.robot.application.RobotModeRecoveryService;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
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
class OperatorRobotModeRecoveryControllerTest {

    private static final String ENDPOINT =
        "/api/v1/operator/robots/bomi-AA001/mode-recoveries";

    @Mock private RobotModeRecoveryService service;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new OperatorRobotModeRecoveryController(service))
            .build();
    }

    @Test
    void validSafetyConfirmationRecoversToIdle() throws Exception {
        UUID robotId = UUID.randomUUID();
        UUID auditId = UUID.randomUUID();
        when(service.recoverToIdle(
            "bomi-AA001", "operator-a", true, "physical inspection completed"))
            .thenReturn(new RobotModeRecoveryResult(
                RobotModeRecoveryDisposition.RECOVERED,
                robotId,
                "bomi-AA001",
                RobotMode.SAFE_STOP,
                RobotMode.IDLE,
                auditId,
                OffsetDateTime.parse("2026-08-05T12:00:00Z"),
                "Robot mode recovered to IDLE"));

        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":true,
                     "reason":"physical inspection completed"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.disposition").value("RECOVERED"))
            .andExpect(jsonPath("$.previousMode").value("SAFE_STOP"))
            .andExpect(jsonPath("$.currentMode").value("IDLE"))
            .andExpect(jsonPath("$.auditId").value(auditId.toString()));
    }

    @Test
    void falsePhysicalSafetyConfirmationIsBadRequest() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":false,"reason":"not inspected"}
                    """))
            .andExpect(status().isBadRequest());

        verify(service, never()).recoverToIdle(
            anyString(), anyString(), anyBoolean(), anyString());
    }

    @Test
    void blankReasonIsBadRequest() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":true,"reason":"  "}
                    """))
            .andExpect(status().isBadRequest());

        verify(service, never()).recoverToIdle(
            anyString(), anyString(), anyBoolean(), anyString());
    }

    @Test
    void missingReasonIsBadRequest() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":true}
                    """))
            .andExpect(status().isBadRequest());

        verify(service, never()).recoverToIdle(
            anyString(), anyString(), anyBoolean(), anyString());
    }

    @Test
    void unknownRobotMapsToNotFound() throws Exception {
        when(service.recoverToIdle(
            "bomi-AA001", "operator-a", true, "registration check"))
            .thenReturn(rejected(
                RobotModeRecoveryDisposition.REJECTED_UNKNOWN_ROBOT,
                null,
                null,
                "Robot is not registered"));

        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":true,"reason":"registration check"}
                    """))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.disposition").value("REJECTED_UNKNOWN_ROBOT"));
    }

    @Test
    void activeScenarioMapsToConflict() throws Exception {
        UUID robotId = UUID.randomUUID();
        when(service.recoverToIdle(
            "bomi-AA001", "operator-a", true, "active scenario check"))
            .thenReturn(rejected(
                RobotModeRecoveryDisposition.REJECTED_ACTIVE_SCENARIO,
                robotId,
                RobotMode.SAFE_STOP,
                "An active scenario exists"));

        mockMvc.perform(post(ENDPOINT)
                .requestAttr(OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE, "operator-a")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"physicalSafetyConfirmed":true,"reason":"active scenario check"}
                    """))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.disposition").value("REJECTED_ACTIVE_SCENARIO"));
    }

    private static RobotModeRecoveryResult rejected(
        RobotModeRecoveryDisposition disposition,
        UUID robotId,
        RobotMode currentMode,
        String message
    ) {
        return new RobotModeRecoveryResult(
            disposition,
            robotId,
            "bomi-AA001",
            currentMode,
            currentMode,
            null,
            null,
            message);
    }
}
