package com.ssafy.bomi.scenario.application;

import java.util.UUID;

/**
 * Hand-off seam from the homecoming flow to the conversation (voice) domain.
 *
 * <p>When a scenario reaches {@code CONVERSING}, the orchestrator calls this to
 * let the voice side take over the dialogue. The MVP ships a logging stub; the
 * voice team provides the real implementation later without touching the
 * orchestrator.</p>
 */
public interface ConversationGateway {

    /** Signals that the robot has greeted the senior and dialogue may begin. */
    void startConversation(UUID scenarioId, UUID seniorId);
}
