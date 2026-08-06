package com.ssafy.bomi.conversation.domain;

/**
 * Priority the robot's utterance was granted by the proactive gate
 * (maps {@code conversation_message.priority}).
 *
 * <p>Only proactive utterances have one. Answering a senior who just spoke needs
 * no permission, so those turns never reach the gate and carry no priority.</p>
 *
 * <p>The values mirror the robot runtime's {@code PRIORITY_POLICY} table, which is
 * the authority on which gates each priority may bypass (CLAUDE.md §7). This enum
 * only records, after the fact, which priority won — behaviour changes belong in
 * that table, not here.</p>
 */
public enum MessagePriority {

    /** Liveness check after a long unexplained silence. Bypasses every gate. */
    CRITICAL,

    /** Time-critical medication such as insulin. Does not interrupt speech. */
    HIGH,

    /** Door greeting. Very short TTL; becomes terse during quiet hours. */
    EVENT,

    /** Re-asking one field of an active {@code fact_candidate}. */
    CLARIFICATION,

    /** Ordinary medication and meal reminders. */
    MEDIUM,

    /** Hydration nudges, gentle check-ins. */
    LOW,

    /** Small talk. First thing dropped under load (CLAUDE.md §18). */
    AMBIENT
}
