package com.ssafy.bomi.conversation.application;

import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.MessagePriority;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.domain.MessageTriggerType;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Records what was said, so the T2 daily summary has something to count.
 *
 * <p><b>Why this service exists.</b> Ticket 203 built read-only context assembly; nothing
 * ever wrote a {@code conversation_message} row from the robot. The T2 metrics
 * {@code senior_utterance_count} and {@code robot_utterance_count} are derived from those
 * rows, so without this path both columns stay NULL forever and the guardian's summary is
 * missing its most basic signal — did anyone talk today.</p>
 *
 * <p><b>The server owns sequence numbers.</b> The robot could not track them reliably: it
 * would have to survive reboots and stay in step with the app writing into the same
 * conversation. So the robot says "this happened next" and the server decides where in the
 * order it lands.</p>
 *
 * <p><b>What this service deliberately does not do.</b> It does not classify. The robot
 * already decided the trigger type, the priority, and whether the utterance was an
 * orientation question; re-deriving any of that from the text here would put the same
 * judgement in two places, and a server that starts analysing conversation content soon
 * does it for other purposes too (CLAUDE.md §8, §9).</p>
 *
 * <p><b>Conversation boundaries are not decided here.</b> {@code resolveConversation} used
 * to just open-or-reuse blindly, which is why every conversation stayed OPEN forever
 * (S15P11E102-254). That judgement — continue, or close the old one and start a new one —
 * now lives in {@link ConversationLifecycleService}, which this service delegates to.</p>
 *
 * @see com.ssafy.bomi.activity.application.DailyActivityMetricService the only consumer
 */
@Service
public class RobotConversationService {

    private final ConversationLifecycleService lifecycleService;
    private final ConversationMessageRepository messageRepository;

    public RobotConversationService(ConversationLifecycleService lifecycleService,
        ConversationMessageRepository messageRepository) {
        this.lifecycleService = lifecycleService;
        this.messageRepository = messageRepository;
    }

    /**
     * Appends one utterance, opening a conversation when the robot has none.
     *
     * @param conversationId the conversation to append to, or {@code null} to open one
     * @param occurredAt when it was said; the robot's normalized clock, not arrival time
     * @param triggerType why this utterance happened — never inferred here
     * @param priority the gate's verdict for a proactive utterance, {@code null} otherwise
     * @param orientationQuestion whether the senior asked "what day is it?", or {@code null}
     *     when the caller does not classify. Null is not false: it means unknown, and the
     *     daily aggregation must not read it as "did not ask"
     * @return the conversation it landed in and the row that was written
     */
    @Transactional
    public RecordedTurn record(UUID seniorId, UUID conversationId, MessageRole role,
        String content, OffsetDateTime occurredAt, MessageTriggerType triggerType,
        MessagePriority priority, Boolean orientationQuestion) {

        UUID targetConversation =
            lifecycleService.openOrContinue(seniorId, conversationId, occurredAt);
        int sequenceNo = nextSequenceNo(targetConversation);

        ConversationMessage message = ConversationMessage.of(
            targetConversation, sequenceNo, role, content, occurredAt);
        applyProvenance(message, role, triggerType, priority, orientationQuestion);

        messageRepository.save(message);
        return new RecordedTurn(targetConversation, message.getId(), sequenceNo);
    }

    private int nextSequenceNo(UUID conversationId) {
        Integer max = messageRepository.findMaxSequenceNo(conversationId);
        return max == null ? 0 : max + 1;
    }

    /**
     * Attaches why the utterance happened.
     *
     * <p>Priority belongs only to robot utterances that passed the gate. A reactive turn
     * never reaches the gate — answering someone who just spoke needs no permission — so
     * carrying a priority on it would invent a decision that was never made
     * (CLAUDE.md §7).</p>
     */
    private void applyProvenance(ConversationMessage message, MessageRole role,
        MessageTriggerType triggerType, MessagePriority priority, Boolean orientationQuestion) {

        if (role == MessageRole.SENIOR) {
            message.attachProvenance(
                triggerType == null ? MessageTriggerType.USER : triggerType, null);
            if (orientationQuestion != null) {
                message.markOrientationQuestion(orientationQuestion);
            }
            return;
        }

        message.attachProvenance(
            triggerType == null ? MessageTriggerType.USER : triggerType, priority);
    }

    /** Where the utterance landed. The robot keeps the conversation id for its next turn. */
    public record RecordedTurn(UUID conversationId, UUID messageId, int sequenceNo) {
    }
}
