package com.ssafy.bomi.conversation.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.conversation.application.ConversationLifecycleService;
import com.ssafy.bomi.conversation.application.RobotConversationService;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;

/**
 * {@code RobotConversationController} 의 {@code POST .../end} 슬라이스 테스트
 * (S15P11E102-254 완료 조건: "대화 종료 API가 상태를 올바르게 바꾼다").
 *
 * <p>{@code RobotFactIntakeControllerTest} 와 같은 모양이다 — 서비스는
 * {@code @MockitoBean} 으로 대체해, 이 테스트는 "요청이 {@code ConversationLifecycleService}
 * 로 올바르게 전달되고, 응답 본문이 새 상태를 담고, {@code IllegalArgumentException} 이
 * 400 으로 바뀌는가"만 본다. 상태 전이 자체(유휴시간 판정, COMPLETED/CANCELLED 분기)의
 * 정확성은 {@code ConversationLifecycleServiceTest} 가 실제 저장소로 검증한다 — 여기서
 * 다시 mock 으로 흉내 내면 그 로직이 옳다는 것은 증명하지 못하고 "서비스가 불렸다"만
 * 증명하게 된다.</p>
 */
@WebMvcTest(RobotConversationController.class)
class RobotConversationControllerTest {

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper objectMapper;

    @MockitoBean RobotConversationService service;
    @MockitoBean ConversationLifecycleService lifecycleService;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID conversationId = UUID.randomUUID();

    @Test
    void endingAConversationReturnsItsNewTerminalStatus() throws Exception {
        Conversation completed = Conversation.open(seniorId);
        completed.end(ConversationStatus.COMPLETED);
        completed.scheduleRawExpiry(OffsetDateTime.now().plusDays(30));
        ReflectionTestUtils.setField(completed, "id", conversationId);
        when(lifecycleService.end(eq(conversationId), eq(seniorId),
            eq(ConversationStatus.COMPLETED), eq(false)))
            .thenReturn(completed);

        mockMvc.perform(post("/api/v1/robot/conversation-events/{id}/end", conversationId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(
                    new EndConversationRequest(seniorId, ConversationStatus.COMPLETED, false))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.conversationId").value(conversationId.toString()))
            .andExpect(jsonPath("$.status").value("COMPLETED"))
            .andExpect(jsonPath("$.endedAt").isNotEmpty())
            .andExpect(jsonPath("$.rawMessagesExpiresAt").isNotEmpty());
    }

    @Test
    void anUnansweredProbeConversationEndsFailed() throws Exception {
        // CLAUDE.md §10 — 무응답 liveness probe 대화는 FAILED 로 닫힌다.
        Conversation failed = Conversation.open(seniorId);
        failed.end(ConversationStatus.FAILED);
        ReflectionTestUtils.setField(failed, "id", conversationId);
        when(lifecycleService.end(eq(conversationId), eq(seniorId),
            eq(ConversationStatus.FAILED), any()))
            .thenReturn(failed);

        mockMvc.perform(post("/api/v1/robot/conversation-events/{id}/end", conversationId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(
                    new EndConversationRequest(seniorId, ConversationStatus.FAILED, null))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("FAILED"));
    }

    @Test
    void unknownConversationIdBecomes400NotInternalError() throws Exception {
        when(lifecycleService.end(eq(conversationId), eq(seniorId),
            eq(ConversationStatus.COMPLETED), any()))
            .thenThrow(new IllegalArgumentException("unknown conversationId: " + conversationId));

        mockMvc.perform(post("/api/v1/robot/conversation-events/{id}/end", conversationId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(
                    new EndConversationRequest(seniorId, ConversationStatus.COMPLETED, false))))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("unknown conversationId: " + conversationId));
    }

    @Test
    void aMissingStatusFailsValidationBeforeReachingTheService() throws Exception {
        String bodyWithoutStatus = """
            {"seniorId":"%s","sealed":false}
            """.formatted(seniorId);

        mockMvc.perform(post("/api/v1/robot/conversation-events/{id}/end", conversationId)
                .contentType(MediaType.APPLICATION_JSON)
                .content(bodyWithoutStatus))
            .andExpect(status().isBadRequest());
    }
}
