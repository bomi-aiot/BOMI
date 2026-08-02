package com.ssafy.bomi.activity.application;

import com.ssafy.bomi.activity.domain.DailyActivityMetric;
import com.ssafy.bomi.care.application.GuardianAlertService;
import com.ssafy.bomi.care.application.GuardianAlertService.AlertOutcome;
import com.ssafy.bomi.care.domain.NotificationTier;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Sends the guardian one summary a day (S15P11E102-211).
 *
 * <p><b>Why once a day and not per event.</b> T2 is a trend, not an incident. Streaming
 * individual events turns care into surveillance and, at the same time, trains the guardian
 * to ignore notifications. The cost of that is their attention when a T1 arrives
 * (CLAUDE.md §9).</p>
 *
 * <p><b>Aggregates and anomalies only.</b> No movement log, no transcript. "She was out
 * unusually long today" is care; "left 14:03, returned 15:20" every day is surveillance.</p>
 *
 * <p><b>Unknown metrics are omitted, not zeroed.</b> A metric we could not measure is left
 * out of the payload entirely, so nothing downstream can render it as a zero.</p>
 */
@Service
public class DailySummaryService {

    private static final Logger log = LoggerFactory.getLogger(DailySummaryService.class);

    private final DailyActivityMetricService metricService;
    private final GuardianAlertService guardianAlertService;

    public DailySummaryService(DailyActivityMetricService metricService,
        GuardianAlertService guardianAlertService) {
        this.metricService = metricService;
        this.guardianAlertService = guardianAlertService;
    }

    /**
     * Aggregates the day and sends it, unless it already went out.
     *
     * <p>Aggregation runs even when the summary was already sent, so a re-run still picks
     * up late-arriving rows. Only the sending is guarded.</p>
     *
     * @return what happened, so a caller (or a test) can tell "sent" from "already sent"
     *     and from "consent refused"
     */
    @Transactional
    public SummaryOutcome sendDailySummary(UUID seniorId, LocalDate metricDate) {
        DailyActivityMetric metric = metricService.aggregate(seniorId, metricDate);

        if (metric.isSummarySent()) {
            // Re-running a batch must not reach the guardian twice. A guardian who receives
            // the same summary twice starts skimming, and skimming is how a T1 gets missed.
            log.info("daily summary for {} on {} already sent at {}; not sending again",
                seniorId, metricDate, metric.getSummarySentAt());
            return new SummaryOutcome(false, "ALREADY_SENT");
        }

        AlertOutcome outcome = guardianAlertService.accept(
            seniorId, NotificationTier.T2, buildPayload(metric));

        if (!outcome.delivered()) {
            // Consent refused, or nobody connected yet. Not marked as sent: if consent is
            // granted tomorrow the summary should still be able to go out.
            log.info("daily summary for {} on {} was not delivered ({})",
                seniorId, metricDate, outcome.reason());
            return new SummaryOutcome(false, outcome.reason());
        }

        metric.markSummarySent(OffsetDateTime.now());
        return new SummaryOutcome(true, null);
    }

    /**
     * Builds the payload, leaving out everything we could not measure.
     *
     * <p>A null metric is dropped rather than sent as 0. If sleep was not measured and we
     * send 0, the guardian reads "did not sleep at all" — a false alarm that costs their
     * trust in every later alert.</p>
     */
    private Map<String, Object> buildPayload(DailyActivityMetric metric) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("reason", "daily_summary");
        payload.put("metricDate", metric.getMetricDate().toString());

        putIfKnown(payload, "medicationTakenCount", metric.getMedicationTakenCount());
        putIfKnown(payload, "medicationScheduledCount", metric.getMedicationScheduledCount());
        putIfKnown(payload, "mealCount", metric.getMealCount());
        putIfKnown(payload, "waterIntakeCount", metric.getWaterIntakeCount());
        putIfKnown(payload, "sleepMinutes", metric.getSleepMinutes());
        putIfKnown(payload, "moodScore", metric.getMoodScore());
        putIfKnown(payload, "seniorUtteranceCount", metric.getSeniorUtteranceCount());
        putIfKnown(payload, "robotUtteranceCount", metric.getRobotUtteranceCount());
        putIfKnown(payload, "outingCount", metric.getOutingCount());
        // Orientation repeats reach the guardian's trend and nothing else. They must never
        // travel back into a prompt, where they would leak into the robot's tone (§8).
        putIfKnown(payload, "orientationQuestionRepeatCount",
            metric.getOrientationQuestionRepeatCount());

        return payload;
    }

    private void putIfKnown(Map<String, Object> payload, String key, Object value) {
        if (value != null) {
            payload.put(key, value);
        }
    }

    /**
     * @param sent false when nothing reached the guardian
     * @param reason why not — {@code ALREADY_SENT}, {@code CONSENT_NOT_GRANTED},
     *     {@code NO_GUARDIAN} — or null when it was sent
     */
    public record SummaryOutcome(boolean sent, String reason) {
    }
}
