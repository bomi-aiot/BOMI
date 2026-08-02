package com.ssafy.bomi.conversation.web;

import com.ssafy.bomi.conversation.domain.MessagePriority;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.domain.MessageTriggerType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * One utterance the robot is reporting.
 *
 * @param conversationId the conversation to append to; {@code null} opens a new one
 * @param occurredAt when it was said. The robot's normalized clock — the Jetson's, not
 *     the server's arrival time, and not the Raspberry Pi's (CLAUDE.md §11, §15). Defaults
 *     to now when absent, which is only correct for turns reported immediately
 * @param triggerType why the utterance happened. The robot decided this; the server does
 *     not infer it from the text
 * @param priority the gate's verdict, for proactive robot utterances only. Null on
 *     reactive turns, which never reach the gate
 * @param orientationQuestion whether the senior asked "what day is it?". <b>Null is not
 *     false</b> — it means the caller does not classify, and the daily aggregation must
 *     not read it as "did not ask"
 */
public record RecordTurnRequest(
    @NotNull UUID seniorId,
    UUID conversationId,
    @NotNull MessageRole role,
    @NotBlank String content,
    OffsetDateTime occurredAt,
    MessageTriggerType triggerType,
    MessagePriority priority,
    Boolean orientationQuestion) {
}
