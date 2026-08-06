package com.ssafy.bomi.conversation.web;

import java.util.UUID;

/**
 * Where the utterance landed.
 *
 * <p>The conversation id comes back even when the robot supplied one, so a robot that
 * started an exchange without an id can keep using the same conversation for the rest
 * of it.</p>
 */
public record RecordTurnResponse(UUID conversationId, UUID messageId, int sequenceNo) {
}
