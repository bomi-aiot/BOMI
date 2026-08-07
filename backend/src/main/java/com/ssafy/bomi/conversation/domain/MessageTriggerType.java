package com.ssafy.bomi.conversation.domain;

/**
 * Why this utterance happened (maps {@code conversation_message.trigger_type}).
 *
 * <p>{@link MessageRole} says <em>who</em> spoke; this says <em>what made them
 * speak</em>. Three things need it: auditing why the robot spoke at 3 a.m.,
 * separating senior from robot volume in the T2 activity metrics, and retrieving
 * the phrasings recently used for a reminder type so the wording can vary
 * (CLAUDE.md §17.8, §19).</p>
 *
 * <p>Nullable on rows written before the column existed: their provenance is
 * genuinely unknown and labelling them all {@code USER} would misclassify robot
 * rows. Every new write must set it.</p>
 */
public enum MessageTriggerType {

    /** The senior spoke first and the robot is answering. Never gated. */
    USER,

    /** A scheduled reminder fired: medication, meals, hydration. */
    SCHEDULE,

    /** A liveness probe from the silence ladder (CLAUDE.md §10). */
    SILENCE_PROBE,

    /** The entrance sensor fired and a greeting was proposed (CLAUDE.md §11). */
    DOOR_EVENT,

    /** Re-asking a field of an active {@code fact_candidate} (CLAUDE.md §12). */
    CLARIFICATION
}
