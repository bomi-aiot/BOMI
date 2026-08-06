package com.ssafy.bomi.config;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.ssafy.bomi.robot.application.RobotModeRecoveryResult;
import com.ssafy.bomi.robot.application.RobotModeRecoveryService;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/** Verifies the registered servlet filter and operator controller as one HTTP boundary. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ActiveProfiles("docs")
@AutoConfigureMockMvc
class OperatorChannelAuthIntegrationTest {

    private static final String ENDPOINT =
        "/api/v1/operator/robots/bomi-AA001/mode-recoveries";
    private static final String BODY = """
        {"physicalSafetyConfirmed":true,"reason":"physical inspection completed"}
        """;

    @Autowired private MockMvc mockMvc;
    @Autowired private OperatorChannelAuthProperties properties;
    @MockitoBean private RobotModeRecoveryService service;

    @BeforeEach
    void resetAuthenticationConfiguration() {
        properties.setSharedSecret("");
        properties.setOperatorId("");
    }

    @AfterEach
    void clearAuthenticationConfiguration() {
        properties.setSharedSecret("");
        properties.setOperatorId("");
    }

    @Test
    void unconfiguredOperatorAuthenticationFailsClosedBeforeController() throws Exception {
        mockMvc.perform(post(ENDPOINT)
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.error").value("SERVICE_UNAVAILABLE"));

        verifyNoInteractions(service);
    }

    @Test
    void missingServerOperatorIdFailsClosedEvenWhenSecretExists() throws Exception {
        properties.setSharedSecret("operator-test-secret");

        mockMvc.perform(post(ENDPOINT)
                .header(OperatorChannelAuthFilter.HEADER_NAME, "operator-test-secret")
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.error").value("SERVICE_UNAVAILABLE"));

        verifyNoInteractions(service);
    }

    @Test
    void configuredEndpointRejectsMissingSecretBeforeController() throws Exception {
        configureAuthentication();

        mockMvc.perform(post(ENDPOINT)
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("UNAUTHORIZED"));

        verifyNoInteractions(service);
    }

    @Test
    void configuredEndpointRejectsWrongSecretBeforeController() throws Exception {
        configureAuthentication();

        mockMvc.perform(post(ENDPOINT)
                .header(OperatorChannelAuthFilter.HEADER_NAME, "wrong-secret")
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("UNAUTHORIZED"));

        verifyNoInteractions(service);
    }

    @Test
    void validSecretDelegatesWithServerConfiguredOperatorId() throws Exception {
        configureAuthentication();
        UUID robotId = UUID.randomUUID();
        UUID auditId = UUID.randomUUID();
        when(service.recoverToIdle(
            "bomi-AA001",
            "server-operator-a",
            true,
            "physical inspection completed"))
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
                .header(OperatorChannelAuthFilter.HEADER_NAME, "operator-test-secret")
                .header("X-Operator-Id", "request-controlled-id-must-be-ignored")
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.disposition").value("RECOVERED"))
            .andExpect(jsonPath("$.auditId").value(auditId.toString()));

        verify(service).recoverToIdle(
            "bomi-AA001",
            "server-operator-a",
            true,
            "physical inspection completed");
    }

    private void configureAuthentication() {
        properties.setSharedSecret("operator-test-secret");
        properties.setOperatorId("server-operator-a");
    }
}
