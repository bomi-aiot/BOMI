package com.ssafy.bomi.fact.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.fact.application.ConversationFactIntakeService;
import com.ssafy.bomi.fact.application.FactCandidateCancellationService;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/**
 * {@link RobotFactIntakeController} 슬라이스 테스트 (S15P11E102-255).
 *
 * <p>서비스는 {@code @MockitoBean} 으로 대체해, 이 테스트는 오직 "요청이 서비스로
 * 올바르게 전달되고, IllegalArgumentException 이 400 으로 바뀌는가"만 본다.</p>
 */
@WebMvcTest(RobotFactIntakeController.class)
class RobotFactIntakeControllerTest {

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper objectMapper;

    @MockitoBean ConversationFactIntakeService service;
    @MockitoBean FactCandidateCancellationService cancellationService;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID conversationId = UUID.randomUUID();
    private final UUID sourceMessageId = UUID.randomUUID();

    private FactCandidateIntakeRequest validRequest() {
        return new FactCandidateIntakeRequest(
                seniorId, conversationId, sourceMessageId, FactTargetDomain.MEMORY,
                "family_event", FactOperation.CREATE, Map.of("content", "손자가 자주 놀러 온다"),
                RiskLevel.NORMAL);
    }

    @Test
    void createsCandidateAndReturns201() throws Exception {
        FactCandidate saved = FactCandidate.fromConversationMessage(
                seniorId, conversationId, sourceMessageId, FactTargetDomain.MEMORY,
                "family_event", FactOperation.CREATE, Map.of("content", "손자가 자주 놀러 온다"),
                RiskLevel.NORMAL);
        // @Id 는 @GeneratedValue 라 실제 저장 전에는 null 이다. 이 테스트는 서비스를
        // mock 으로 대체해 저장을 거치지 않으므로, 컨트롤러가 그대로 내보내는 값을
        // 검증하기 위해 id 를 직접 채워 넣는다.
        UUID savedId = UUID.randomUUID();
        org.springframework.test.util.ReflectionTestUtils.setField(saved, "id", savedId);
        when(service.intake(eq(seniorId), eq(conversationId), eq(sourceMessageId),
                eq(FactTargetDomain.MEMORY), eq("family_event"), eq(FactOperation.CREATE),
                any(), eq(RiskLevel.NORMAL))).thenReturn(saved);

        mockMvc.perform(post("/api/v1/robot/fact-candidates")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(savedId.toString()))
                .andExpect(jsonPath("$.status").value("CAPTURED"));
    }

    @Test
    void badReferenceBecomes400NotInternalError() throws Exception {
        when(service.intake(eq(seniorId), eq(conversationId), eq(sourceMessageId),
                eq(FactTargetDomain.MEMORY), eq("family_event"), eq(FactOperation.CREATE),
                any(), eq(RiskLevel.NORMAL)))
                .thenThrow(new IllegalArgumentException(
                        "conversation " + conversationId + " does not belong to senior " + seniorId));

        mockMvc.perform(post("/api/v1/robot/fact-candidates")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value(
                        "conversation " + conversationId + " does not belong to senior " + seniorId));
    }

    @Test
    void blankFactTypeFailsValidation() throws Exception {
        FactCandidateIntakeRequest invalid = new FactCandidateIntakeRequest(
                seniorId, conversationId, sourceMessageId, FactTargetDomain.MEMORY,
                "   ", FactOperation.CREATE, Map.of("content", "x"), RiskLevel.NORMAL);

        mockMvc.perform(post("/api/v1/robot/fact-candidates")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(invalid)))
                .andExpect(status().isBadRequest());
    }
}
