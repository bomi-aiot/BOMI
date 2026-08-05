package com.ssafy.bomi.fact.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactSourceType;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/**
 * {@link ConversationFactIntakeService} 단위 테스트 (S15P11E102-255).
 *
 * <p>실제 DB 대신 리포지토리를 목(mock)으로 대체한다 — 이 서비스가 검증해야 하는
 * 것은 "다른 사람의 대화/메시지를 걸러내는가"이지 JPA 매핑 자체가 아니어서,
 * {@code RobotObservationServiceTest} 와 같은 스타일을 따른다.</p>
 */
class ConversationFactIntakeServiceTest {

    private final ConversationRepository conversationRepository = mock(ConversationRepository.class);
    private final ConversationMessageRepository conversationMessageRepository =
            mock(ConversationMessageRepository.class);
    private final FactCandidateRepository factCandidateRepository = mock(FactCandidateRepository.class);

    private ConversationFactIntakeService service;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID conversationId = UUID.randomUUID();
    private final UUID sourceMessageId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        service = new ConversationFactIntakeService(
                conversationRepository, conversationMessageRepository, factCandidateRepository);
    }

    private Conversation conversationOf(UUID owner) {
        return Conversation.open(owner);
    }

    private ConversationMessage messageIn(UUID inConversationId) {
        return ConversationMessage.of(
                inConversationId, 0, MessageRole.SENIOR, "요즘 손자가 자주 놀러 와요", OffsetDateTime.now());
    }

    @Test
    void capturesCandidateWhenConversationAndMessageBelongToSenior() {
        when(conversationRepository.findById(conversationId))
                .thenReturn(Optional.of(conversationOf(seniorId)));
        when(conversationMessageRepository.findById(sourceMessageId))
                .thenReturn(Optional.of(messageIn(conversationId)));
        when(factCandidateRepository.save(any(FactCandidate.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        FactCandidate saved = service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "손자가 자주 놀러 온다"), RiskLevel.NORMAL);

        assertThat(saved.getSourceType()).isEqualTo(FactSourceType.CONVERSATION_MESSAGE);
        assertThat(saved.getSeniorId()).isEqualTo(seniorId);
        assertThat(saved.getConversationId()).isEqualTo(conversationId);
        assertThat(saved.getSourceMessageId()).isEqualTo(sourceMessageId);
        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.CAPTURED);

        ArgumentCaptor<FactCandidate> captor = ArgumentCaptor.forClass(FactCandidate.class);
        org.mockito.Mockito.verify(factCandidateRepository).save(captor.capture());
        assertThat(captor.getValue().getProposedValue()).containsEntry("content", "손자가 자주 놀러 온다");
    }

    @Test
    void rejectsConversationThatBelongsToAnotherSenior() {
        UUID otherSenior = UUID.randomUUID();
        when(conversationRepository.findById(conversationId))
                .thenReturn(Optional.of(conversationOf(otherSenior)));

        assertThatThrownBy(() -> service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "x"), RiskLevel.NORMAL))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(conversationId.toString())
                .hasMessageContaining(seniorId.toString());

        org.mockito.Mockito.verifyNoInteractions(factCandidateRepository);
    }

    @Test
    void rejectsUnknownConversationId() {
        when(conversationRepository.findById(conversationId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "x"), RiskLevel.NORMAL))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(conversationId.toString());

        org.mockito.Mockito.verifyNoInteractions(factCandidateRepository);
    }

    @Test
    void rejectsMessageThatBelongsToAnotherConversation() {
        UUID otherConversationId = UUID.randomUUID();
        when(conversationRepository.findById(conversationId))
                .thenReturn(Optional.of(conversationOf(seniorId)));
        when(conversationMessageRepository.findById(sourceMessageId))
                .thenReturn(Optional.of(messageIn(otherConversationId)));

        assertThatThrownBy(() -> service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "x"), RiskLevel.NORMAL))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(sourceMessageId.toString())
                .hasMessageContaining(conversationId.toString());

        org.mockito.Mockito.verifyNoInteractions(factCandidateRepository);
    }

    @Test
    void rejectsUnknownSourceMessageId() {
        when(conversationRepository.findById(conversationId))
                .thenReturn(Optional.of(conversationOf(seniorId)));
        when(conversationMessageRepository.findById(sourceMessageId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "x"), RiskLevel.NORMAL))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(sourceMessageId.toString());

        org.mockito.Mockito.verifyNoInteractions(factCandidateRepository);
    }
}
