package com.ssafy.bomi.scenario.application;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.scenario.config.AiConversationProperties;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class AiConversationTimeoutWatchdogTest {

    @Test
    void usesTenSecondAndFiveMinuteCutoffsWithoutSleeping() {
        Clock clock = Clock.fixed(Instant.parse("2026-08-05T01:00:00Z"), ZoneOffset.UTC);
        OffsetDateTime now = OffsetDateTime.now(clock);
        ConversationRepository repository = mock(ConversationRepository.class);
        HomecomingOrchestrator orchestrator = mock(HomecomingOrchestrator.class);
        AiConversationProperties properties = new AiConversationProperties();
        Conversation pending = requestedAt(now.minusSeconds(10));
        Conversation active = requestedAt(now.minusMinutes(6));
        active.markAiStarted(now.minusMinutes(5));

        when(repository
            .findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNullAndStartedAtLessThanEqual(
                eq(ConversationStatus.OPEN), eq(now.minusSeconds(10))))
            .thenReturn(List.of(pending));
        when(repository
            .findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNotNullAndAiStartedAtLessThanEqual(
                eq(ConversationStatus.OPEN), eq(now.minusMinutes(5))))
            .thenReturn(List.of(active));
        AiConversationTimeoutWatchdog watchdog = new AiConversationTimeoutWatchdog(
            repository, orchestrator, properties, clock);

        watchdog.tick();

        verify(orchestrator).onConversationStartTimedOut(pending.getId());
        verify(orchestrator).onConversationActiveTimedOut(active.getId());
    }

    private Conversation requestedAt(OffsetDateTime at) {
        Conversation conversation = Conversation.requestForScenario(
            UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID().toString(), at);
        ReflectionTestUtils.setField(conversation, "id", UUID.randomUUID());
        return conversation;
    }
}
