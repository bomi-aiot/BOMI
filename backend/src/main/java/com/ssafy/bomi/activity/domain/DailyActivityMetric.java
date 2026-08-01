package com.ssafy.bomi.activity.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * One day of aggregated activity for one senior (maps table
 * {@code daily_activity_metric}).
 *
 * <p>What the T2 daily summary reads as a time series. The guardian receives
 * aggregates and anomalies only — never raw movement or conversation logs
 * (CLAUDE.md §9, §11).</p>
 *
 * <p><strong>Every metric is nullable, and null does not mean zero.</strong> This
 * is the most important property of this table. If sleep was not measured and we
 * store 0, the T2 trend tells the guardian the senior did not sleep at all. False
 * positives like that make guardians stop reading alerts, and that is when a real
 * emergency gets missed — a noisy detector is a safety failure, not an
 * annoyance.</p>
 *
 * <p>Aggregates only, one row per senior per local day. We deliberately do not
 * store every periodic measurement: it would bloat the schema and, on the robot
 * side, wear out the microSD card (CLAUDE.md §18).</p>
 */
@Entity
@Table(
    name = "daily_activity_metric",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_daily_activity_metric_day",
        columnNames = {"senior_id", "metric_date"}))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class DailyActivityMetric {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    /**
     * The senior's <em>local</em> date, computed with {@code app_user.time_zone}.
     * Using UTC would push activity near midnight into the wrong day and skew
     * every trend built on this table.
     */
    @Column(name = "metric_date", nullable = false)
    private LocalDate metricDate;

    /**
     * Adherence as numerator and denominator rather than a rate, so the report can
     * say "3 of 4" and so we never compute a rate for a day with nothing scheduled.
     */
    @Column(name = "medication_taken_count")
    private Short medicationTakenCount;

    @Column(name = "medication_scheduled_count")
    private Short medicationScheduledCount;

    @Column(name = "meal_count")
    private Short mealCount;

    @Column(name = "water_intake_count")
    private Short waterIntakeCount;

    @Column(name = "sleep_minutes")
    private Integer sleepMinutes;

    /** 1–5, estimated from conversation. An observation, never a diagnosis. */
    @Column(name = "mood_score")
    private Short moodScore;

    /**
     * Senior and robot volume are counted separately. Counting them together would
     * score a day when the robot talked to itself as an active day.
     * {@code conversation_message.trigger_type} is what makes the split possible.
     */
    @Column(name = "senior_utterance_count")
    private Integer seniorUtteranceCount;

    @Column(name = "robot_utterance_count")
    private Integer robotUtteranceCount;

    /** Aggregated from {@code occupancy_event}. A second activity signal besides speech. */
    @Column(name = "outing_count")
    private Short outingCount;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    private DailyActivityMetric(UUID seniorId, LocalDate metricDate) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.metricDate = requireNonNull(metricDate, "metricDate");
    }

    /**
     * Opens an empty row for a senior's local day. Every metric starts null, which
     * correctly reads as "not measured yet" rather than "measured as zero".
     */
    public static DailyActivityMetric openDay(UUID seniorId, LocalDate metricDate) {
        return new DailyActivityMetric(seniorId, metricDate);
    }

    /** Records medication adherence for the day as taken-of-scheduled. */
    public void recordAdherence(Short takenCount, Short scheduledCount) {
        this.medicationTakenCount = takenCount;
        this.medicationScheduledCount = scheduledCount;
    }

    /** Records the day's self-care counts. Any argument may be {@code null} for "unknown". */
    public void recordSelfCare(Short mealCount, Short waterIntakeCount, Integer sleepMinutes) {
        this.mealCount = mealCount;
        this.waterIntakeCount = waterIntakeCount;
        this.sleepMinutes = sleepMinutes;
    }

    /** Records conversation volume, split so robot chatter is not read as senior activity. */
    public void recordConversationVolume(Integer seniorUtteranceCount, Integer robotUtteranceCount) {
        this.seniorUtteranceCount = seniorUtteranceCount;
        this.robotUtteranceCount = robotUtteranceCount;
    }

    /** Records the mood estimate (1–5) and how many times the senior went out. */
    public void recordMoodAndOutings(Short moodScore, Short outingCount) {
        this.moodScore = moodScore;
        this.outingCount = outingCount;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
