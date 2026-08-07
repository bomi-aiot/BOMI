package com.ssafy.bomi.activity.application;

import com.ssafy.bomi.activity.domain.DailyActivityMetric;
import com.ssafy.bomi.activity.repository.DailyActivityMetricRepository;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import com.ssafy.bomi.occupancy.repository.OccupancyEventRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Rolls one senior's day into a single row (S15P11E102-211).
 *
 * <p><b>Unknown is not zero.</b> This is the rule the whole table is built around, and it
 * decides what this service is allowed to write. A metric we could not measure stays null.
 * Storing 0 for unmeasured sleep tells the guardian the senior did not sleep at all, and
 * false alarms like that teach guardians to skim — which is exactly when a real emergency
 * gets missed (CLAUDE.md §9).</p>
 *
 * <p><b>Local dates, not UTC.</b> A day boundary computed in UTC pushes late-evening
 * activity into tomorrow for a Korean senior, and every trend built on the table inherits
 * the error.</p>
 *
 * <p><b>Idempotent.</b> Batches get re-run — restarts, manual triggers, a scheduler firing
 * twice. Re-running recomputes the same row rather than adding one; the unique constraint
 * on {@code (senior_id, metric_date)} is the backstop.</p>
 */
@Service
public class DailyActivityMetricService {

    private static final Logger log = LoggerFactory.getLogger(DailyActivityMetricService.class);

    /** Care-record type written when the senior takes a medication (S15P11E102-224). */
    private static final String MEDICATION_TAKEN = "MEDICATION_TAKEN";

    private final DailyActivityMetricRepository metricRepository;
    private final ConversationMessageRepository messageRepository;
    private final OccupancyEventRepository occupancyEventRepository;
    private final CareRecordRepository careRecordRepository;
    private final AppUserRepository appUserRepository;

    public DailyActivityMetricService(DailyActivityMetricRepository metricRepository,
        ConversationMessageRepository messageRepository,
        OccupancyEventRepository occupancyEventRepository,
        CareRecordRepository careRecordRepository,
        AppUserRepository appUserRepository) {
        this.metricRepository = metricRepository;
        this.messageRepository = messageRepository;
        this.occupancyEventRepository = occupancyEventRepository;
        this.careRecordRepository = careRecordRepository;
        this.appUserRepository = appUserRepository;
    }

    /**
     * Computes (or recomputes) one senior's row for one of their local days.
     *
     * @param metricDate the senior's local date, not the server's
     */
    @Transactional
    public DailyActivityMetric aggregate(UUID seniorId, LocalDate metricDate) {
        ZoneId zone = zoneOf(seniorId);
        OffsetDateTime from = metricDate.atStartOfDay(zone).toOffsetDateTime();
        OffsetDateTime to = metricDate.plusDays(1).atStartOfDay(zone).toOffsetDateTime();

        DailyActivityMetric metric = metricRepository
            .findBySeniorIdAndMetricDate(seniorId, metricDate)
            .orElseGet(() -> metricRepository.save(
                DailyActivityMetric.openDay(seniorId, metricDate)));

        List<ConversationMessage> messages =
            messageRepository.findForSeniorBetween(seniorId, from, to);
        applyConversationMetrics(metric, messages);

        long outings = occupancyEventRepository
            .countBySeniorIdAndDirectionAndOccurredAtGreaterThanEqualAndOccurredAtLessThan(
                seniorId, OccupancyDirection.OUT, from, to);
        // Mood is not estimated yet, so it stays null rather than becoming a made-up 3.
        metric.recordMoodAndOutings(null, (short) outings);

        metric.recordAdherence(countMedicationTaken(seniorId, from, to), scheduledCount());

        log.debug("aggregated {} for {}: {} senior / {} robot utterances, {} outings",
            metricDate, seniorId, metric.getSeniorUtteranceCount(),
            metric.getRobotUtteranceCount(), outings);
        return metric;
    }

    /**
     * Splits speech volume by who spoke and counts orientation repeats.
     *
     * <p>Counting senior and robot together would score a day when the robot talked to
     * itself as an active day. {@code role} is what makes the split possible.</p>
     *
     * <p>Orientation questions are counted only where the robot said so. A null flag means
     * "not classified", and treating it as false would quietly report a decline as an
     * improvement.</p>
     */
    private void applyConversationMetrics(DailyActivityMetric metric,
        List<ConversationMessage> messages) {

        if (messages.isEmpty()) {
            // No rows can mean two very different things: nobody talked, or the robot was
            // offline and never reported. We cannot tell them apart here, so we leave the
            // columns alone rather than writing a zero that reads as "silent all day".
            log.info("no conversation rows for {} on {}; leaving volume metrics unset",
                metric.getSeniorId(), metric.getMetricDate());
            return;
        }

        int seniorCount = 0;
        int robotCount = 0;
        int orientationRepeats = 0;
        for (ConversationMessage message : messages) {
            if (message.getRole() == MessageRole.SENIOR) {
                seniorCount++;
                if (Boolean.TRUE.equals(message.getOrientationQuestion())) {
                    orientationRepeats++;
                }
            } else {
                robotCount++;
            }
        }

        metric.recordConversationVolume(seniorCount, robotCount);
        metric.recordOrientationRepeats((short) orientationRepeats);
    }

    /**
     * How many doses the senior actually took that day.
     *
     * <p>One counting query against {@code (senior_id, record_type, occurred_at)}. It used
     * to load every care record the senior had ever had and parse {@code details} JSON in
     * Java, because the table had no timestamp column at all — the reason V7 exists
     * (S15P11E102-230). That worked while the table was small and got worse every day this
     * batch ran.</p>
     *
     * <p>Records with no {@code occurred_at} fall outside the range and are not counted.
     * That is deliberate: attributing a dose to the wrong day is worse than not counting
     * it, because the guardian would see adherence the senior never had.</p>
     */
    private Short countMedicationTaken(UUID seniorId, OffsetDateTime from, OffsetDateTime to) {
        return (short) careRecordRepository
            .countByTypeBetween(seniorId, MEDICATION_TAKEN, from, to);
    }

    /**
     * The denominator stays null, on purpose.
     *
     * <p>Working out how many doses were scheduled for a given day means expanding
     * recurrence rules, and {@code CareRecordQueryService} (S15P11E102-224) already does
     * that for today. Reimplementing it here would put the same rule in two places, and
     * the two would drift — the guardian would then see one adherence number on the
     * dashboard and a different one in the summary.</p>
     *
     * <p>Null is the honest answer meanwhile: the summary can say "took 3" and simply not
     * claim a ratio. That is why V4 stores numerator and denominator separately.</p>
     */
    private Short scheduledCount() {
        return null;
    }

    /**
     * The senior's own time zone, falling back to the server's.
     *
     * <p>The fallback is logged. A silently wrong zone shifts every day boundary and the
     * resulting trend looks plausible, which makes it the worst kind of wrong.</p>
     */
    private ZoneId zoneOf(UUID seniorId) {
        String configured = appUserRepository.findById(seniorId)
            .map(AppUser::getTimeZone)
            .orElse(null);
        if (configured == null || configured.isBlank()) {
            log.warn("senior {} has no time zone; day boundaries fall back to the server's",
                seniorId);
            return ZoneId.systemDefault();
        }
        try {
            return ZoneId.of(configured);
        } catch (Exception error) {
            log.warn("senior {} has an unreadable time zone '{}'; falling back to the server's",
                seniorId, configured);
            return ZoneId.systemDefault();
        }
    }
}
