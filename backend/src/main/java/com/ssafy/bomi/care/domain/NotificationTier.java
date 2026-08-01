package com.ssafy.bomi.care.domain;

/**
 * Urgency and privacy routing for an outbound guardian notification
 * (maps {@code care_record.notification_tier}).
 *
 * <p>These tiers are the product's ethics, not a notification setting. A robot
 * that reports everything to your children is a robot you stop confiding in, and
 * then the emotional pillar dies (CLAUDE.md §9).</p>
 *
 * <p>There is deliberately no {@code T4} value here. T4 means "never sent", so no
 * notification record is created at all; it is expressed as
 * {@code memory.visibility = PRIVATE} (senior-only). A T4 constant on a
 * notification would invite code that "sends a T4".</p>
 *
 * <p>Not to be confused with the consent columns on {@code app_user} or with
 * {@code fact_candidate} confirmation. Those answer "may we store this?" and
 * "is this fact correct?"; this answers "how urgently does the guardian hear it?"</p>
 */
public enum NotificationTier {

    /**
     * Explicit danger, an explicit request for help, prolonged non-response, or a
     * self-harm signal. Delivered immediately and <strong>regardless of
     * {@code guardian_sharing_consent_status}</strong>, because it is life safety.
     * That override is a deliberate product decision and must be stated plainly
     * in the consent copy so it is never a surprise.
     */
    T1,

    /**
     * Adherence, meals, water, sleep, activity level, outing frequency, mild mood
     * trend. Sent as one daily batch. Notification, not permission — but still
     * checks sharing consent.
     */
    T2,

    /**
     * Accumulated depression signals, loneliness, bereavement, family conflict.
     * Requires consent, asked later at a natural moment. Interrupting a
     * confession with "shall I report this?" is the worst possible move.
     */
    T3
}
