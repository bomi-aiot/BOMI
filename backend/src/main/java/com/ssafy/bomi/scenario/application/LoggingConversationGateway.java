package com.ssafy.bomi.scenario.application;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * MVP stub {@link ConversationGateway} that only logs the hand-off. Replaced by
 * the voice domain's real implementation in a later ticket.
 */
@Component
public class LoggingConversationGateway implements ConversationGateway {

    private static final Logger log = LoggerFactory.getLogger(LoggingConversationGateway.class);

    @Override
    public void startConversation(UUID scenarioId, UUID seniorId) {
        log.info("Conversation hand-off (stub): scenarioId={}, seniorId={}", scenarioId, seniorId);
    }
}
