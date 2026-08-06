package com.ssafy.bomi.guardian;

import static org.hamcrest.Matchers.nullValue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.guardian.dto.GuardianWalkRequest;
import com.ssafy.bomi.scenario.application.WalkOrchestrator;
import com.ssafy.bomi.scenario.application.WalkRequestResult;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestDisposition;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/** HTTP adapter contract for Guardian walk requests. */
@WebMvcTest(GuardianWalkRequestController.class)
class GuardianWalkRequestControllerTest {

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper objectMapper;

    @MockitoBean WalkOrchestrator orchestrator;

    @Test
    void acceptedStartReturns202AndCorrelation() throws Exception {
        UUID scenarioId = UUID.randomUUID();
        org.mockito.Mockito.when(orchestrator.handleGuardianRequest(
                "app-start-001", "bomi-AA001", WalkAction.START))
            .thenReturn(result(
                "app-start-001", WalkAction.START, true, scenarioId,
                ScenarioStatus.STARTING_FOLLOW, null, false,
                WalkRequestDisposition.ACCEPTED));

        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(new GuardianWalkRequest(
                    "app-start-001", "bomi-AA001", WalkAction.START))))
            .andExpect(status().isAccepted())
            .andExpect(jsonPath("$.requestId").value("app-start-001"))
            .andExpect(jsonPath("$.action").value("START"))
            .andExpect(jsonPath("$.accepted").value(true))
            .andExpect(jsonPath("$.scenarioId").value(scenarioId.toString()))
            .andExpect(jsonPath("$.status").value("STARTING_FOLLOW"))
            .andExpect(jsonPath("$.reasonCode").value(nullValue()))
            .andExpect(jsonPath("$.duplicate").value(false));

        verify(orchestrator).handleGuardianRequest(
            "app-start-001", "bomi-AA001", WalkAction.START);
    }

    @Test
    void duplicateAcceptedRequestKeeps202AndMarksReplay() throws Exception {
        UUID scenarioId = UUID.randomUUID();
        org.mockito.Mockito.when(orchestrator.handleGuardianRequest(
                "app-start-duplicate", "bomi-AA001", WalkAction.START))
            .thenReturn(result(
                "app-start-duplicate", WalkAction.START, true, scenarioId,
                ScenarioStatus.STARTING_FOLLOW, null, true,
                WalkRequestDisposition.ACCEPTED));

        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"requestId":"app-start-duplicate","robotId":"bomi-AA001","action":"START"}
                    """))
            .andExpect(status().isAccepted())
            .andExpect(jsonPath("$.scenarioId").value(scenarioId.toString()))
            .andExpect(jsonPath("$.status").value("STARTING_FOLLOW"))
            .andExpect(jsonPath("$.duplicate").value(true));
    }

    @Test
    void stopWithoutActiveWalkReturnsDeterministic200NoOp() throws Exception {
        org.mockito.Mockito.when(orchestrator.handleGuardianRequest(
                "app-stop-none", "bomi-AA001", WalkAction.STOP))
            .thenReturn(result(
                "app-stop-none", WalkAction.STOP, false, null, null,
                "NO_ACTIVE_WALK", false,
                WalkRequestDisposition.REJECTED_NO_ACTIVE_WALK));

        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"requestId":"app-stop-none","robotId":"bomi-AA001","action":"STOP"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.action").value("STOP"))
            .andExpect(jsonPath("$.accepted").value(false))
            .andExpect(jsonPath("$.scenarioId").value(nullValue()))
            .andExpect(jsonPath("$.status").value(nullValue()))
            .andExpect(jsonPath("$.reasonCode").value("NO_ACTIVE_WALK"));
    }

    @Test
    void unknownRobotReturns404() throws Exception {
        org.mockito.Mockito.when(orchestrator.handleGuardianRequest(
                "app-unknown", "unknown-robot", WalkAction.START))
            .thenReturn(result(
                "app-unknown", WalkAction.START, false, null, null,
                "UNKNOWN_ROBOT", false,
                WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT));

        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"requestId":"app-unknown","robotId":"unknown-robot","action":"START"}
                    """))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.accepted").value(false))
            .andExpect(jsonPath("$.reasonCode").value("UNKNOWN_ROBOT"));
    }

    @Test
    void policyConflictReturns409() throws Exception {
        org.mockito.Mockito.when(orchestrator.handleGuardianRequest(
                "app-rest-guard", "bomi-AA001", WalkAction.START))
            .thenReturn(result(
                "app-rest-guard", WalkAction.START, false, null, null,
                "REST_GUARD", false,
                WalkRequestDisposition.REJECTED_REST_GUARD));

        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"requestId":"app-rest-guard","robotId":"bomi-AA001","action":"START"}
                    """))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.accepted").value(false))
            .andExpect(jsonPath("$.reasonCode").value("REST_GUARD"));
    }

    @Test
    void unavailableMqttCommandGatewayReturns503() throws Exception {
        org.mockito.Mockito.when(orchestrator.handleGuardianRequest(
                "app-unavailable", "bomi-AA001", WalkAction.START))
            .thenReturn(result(
                "app-unavailable", WalkAction.START, false, null, null,
                "MQTT_UNAVAILABLE", false,
                WalkRequestDisposition.REJECTED_MQTT_UNAVAILABLE));

        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"requestId":"app-unavailable","robotId":"bomi-AA001","action":"START"}
                    """))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.accepted").value(false))
            .andExpect(jsonPath("$.reasonCode").value("MQTT_UNAVAILABLE"));
    }

    @Test
    void clientSourceCannotOverrideServerAssignedAppSource() throws Exception {
        UUID scenarioId = UUID.randomUUID();
        org.mockito.Mockito.when(orchestrator.handleGuardianRequest(
                "app-forced-source", "bomi-AA001", WalkAction.START))
            .thenReturn(result(
                "app-forced-source", WalkAction.START, true, scenarioId,
                ScenarioStatus.STARTING_FOLLOW, null, false,
                WalkRequestDisposition.ACCEPTED));

        // GuardianWalkRequest has no source field. Even if a client sends one, the
        // controller can only invoke handleGuardianRequest(), whose service boundary fixes APP.
        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "requestId":"app-forced-source",
                      "robotId":"bomi-AA001",
                      "action":"START",
                      "source":"VOICE"
                    }
                    """))
            .andExpect(status().isAccepted());

        verify(orchestrator).handleGuardianRequest(
            "app-forced-source", "bomi-AA001", WalkAction.START);
    }

    @Test
    void malformedRequestsFailValidationBeforeApplicationService() throws Exception {
        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"requestId":"   ","robotId":"bad robot/id","action":null}
                    """))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(orchestrator);
    }

    @Test
    void requestIdLongerThan64CharactersFailsValidation() throws Exception {
        String requestId = "r".repeat(65);

        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(new GuardianWalkRequest(
                    requestId, "bomi-AA001", WalkAction.START))))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(orchestrator);
    }

    @Test
    void unknownActionFailsJsonBinding() throws Exception {
        mockMvc.perform(post("/api/v1/guardian/walk-requests")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"requestId":"app-invalid-action","robotId":"bomi-AA001","action":"PAUSE"}
                    """))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(orchestrator);
    }

    private static WalkRequestResult result(
        String requestId,
        WalkAction action,
        boolean accepted,
        UUID scenarioId,
        ScenarioStatus status,
        String reasonCode,
        boolean duplicate,
        WalkRequestDisposition disposition
    ) {
        return new WalkRequestResult(
            requestId, action, accepted, scenarioId, status,
            reasonCode, duplicate, disposition);
    }
}
