package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.scenario.config.AiConversationProperties;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** Recovers conversations that AI did not start within 10 seconds or end within five minutes. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class AiConversationTimeoutWatchdog {

    private static final Logger log = LoggerFactory.getLogger(AiConversationTimeoutWatchdog.class);

    private final ConversationRepository conversationRepository;
    private final HomecomingOrchestrator orchestrator;
    private final AiConversationProperties properties;
    private final Clock clock;

    public AiConversationTimeoutWatchdog(
        ConversationRepository conversationRepository,
        HomecomingOrchestrator orchestrator,
        AiConversationProperties properties,
        Clock clock
    ) {
        this.conversationRepository = conversationRepository;
        this.orchestrator = orchestrator;
        this.properties = properties;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${bomi.ai-conversation.timeout-check-interval-millis:1000}")
    public void tick() {
        try {
            OffsetDateTime now = OffsetDateTime.now(clock);
            List<Conversation> pending = conversationRepository
                .findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNullAndStartedAtLessThanEqual(
                    ConversationStatus.OPEN, now.minus(properties.getStartTimeout()));
            expireEach(pending, orchestrator::onConversationStartTimedOut);

            List<Conversation> active = conversationRepository
                .findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNotNullAndAiStartedAtLessThanEqual(
                    ConversationStatus.OPEN, now.minus(properties.getMaxDuration()));
            expireEach(active, orchestrator::onConversationActiveTimedOut);
        } catch (RuntimeException ex) {
            log.error("AI conversation timeout watchdog tick failed; will retry", ex);
        }
    }

    private void expireEach(List<Conversation> conversations, Consumer<java.util.UUID> action) {
        for (Conversation conversation : conversations) {
            try {
                action.accept(conversation.getId());
            } catch (RuntimeException ex) {
                log.error("Could not recover timed-out AI conversation: conversationId={}",
                    conversation.getId(), ex);
            }
        }
    }
}
