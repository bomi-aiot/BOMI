package com.ssafy.bomi.care.domain;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Works out a care record's {@code occurred_at} from its {@code details} (S15P11E102-230).
 *
 * <p><b>Why this exists as one class.</b> {@code V7__add_care_record_occurred_at.sql}
 * backfilled the column from four different keys, and the write paths have to derive it
 * the same way or old rows and new rows end up on different clocks. Spreading that rule
 * across five services is how they drift. <b>If you change the order here, change the
 * {@code COALESCE} in V7 to match</b> — the two are one rule written twice, once for rows
 * that already existed and once for rows still to come.</p>
 *
 * <p><b>Why the keys stay in {@code details} at all.</b> The robot and the app still send
 * them, and the dashboard still renders some of them verbatim. They are being retired, but
 * the column has to be trusted everywhere first — a half-finished migration that deletes
 * the fallback is worse than two sources that agree.</p>
 */
public final class CareRecordTime {

    private static final Logger log = LoggerFactory.getLogger(CareRecordTime.class);

    /**
     * The senior's zone, for the one key that carries a bare date.
     *
     * <p>Hard-coded because the MVP serves one Korean household, the same assumption
     * {@code CareRecordQueryService} and {@code DashboardService} already make. It matters:
     * reading a {@code metricDate} as UTC midnight would file a Korean senior's daily
     * summary under the previous day.</p>
     */
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    private CareRecordTime() {
    }

    /**
     * Reads the time out of {@code details}, or null when there is none to read.
     *
     * <p>Order matches V7: the most specific convention wins. No record carries two of
     * these keys today, but naming the order means a future one has a defined answer.</p>
     *
     * <ul>
     *   <li>{@code scheduledAt} — ISO string. The dose slot a MEDICATION_TAKEN matched</li>
     *   <li>{@code startsAt} — ISO string. When an appointment or schedule begins</li>
     *   <li>{@code observedAt} — ISO string. When a sensor reading was taken</li>
     *   <li>{@code ts} — epoch seconds. What the robot's outbox stamps on an alert</li>
     *   <li>{@code metricDate} — ISO date. The daily summary's day, read as its start</li>
     * </ul>
     *
     * <p><b>Unreadable means null, never "now".</b> A value we cannot parse is a value we
     * do not know, and guessing puts an old alert at the top of the guardian's screen or a
     * missed dose into today's adherence.</p>
     */
    public static OffsetDateTime fromDetails(Map<String, Object> details) {
        if (details == null || details.isEmpty()) {
            return null;
        }
        OffsetDateTime iso = firstIso(details, "scheduledAt", "startsAt", "observedAt");
        if (iso != null) {
            return iso;
        }
        OffsetDateTime epoch = fromEpochSeconds(details.get("ts"));
        if (epoch != null) {
            return epoch;
        }
        return fromLocalDate(details.get("metricDate"));
    }

    /**
     * {@link #fromDetails} with a fallback for records that are happening right now.
     *
     * <p>Used by the paths where "we are recording this because it just happened" is true
     * by construction — an alert arriving from the robot, an observation being reported, a
     * fact being confirmed. There, the current time is not a guess.</p>
     *
     * <p>Do <b>not</b> reach for this to paper over a missing key on a record that
     * describes some other moment. That is the case where null is the honest answer.</p>
     */
    public static OffsetDateTime fromDetailsOrNow(Map<String, Object> details,
        OffsetDateTime now) {
        OffsetDateTime derived = fromDetails(details);
        return derived != null ? derived : now;
    }

    private static OffsetDateTime firstIso(Map<String, Object> details, String... keys) {
        for (String key : keys) {
            OffsetDateTime parsed = parseIso(details.get(key), key);
            if (parsed != null) {
                return parsed;
            }
        }
        return null;
    }

    private static OffsetDateTime parseIso(Object raw, String key) {
        if (!(raw instanceof String text) || text.isBlank()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(text);
        } catch (RuntimeException error) {
            log.warn("care record details.{} is not a readable timestamp: '{}'", key, text);
            return null;
        }
    }

    private static OffsetDateTime fromEpochSeconds(Object raw) {
        // 로봇의 발신 큐는 숫자로 싣지만, JSON 을 거치며 문자열이 되어 오는 경로도 있다.
        // 두 형태를 다 받는다 — 여기서 받아주지 않으면 알림이 시각 없이 저장되고,
        // 보호자 화면에서 정렬 맨 뒤로 밀린다.
        Double seconds = null;
        if (raw instanceof Number number) {
            seconds = number.doubleValue();
        } else if (raw instanceof String text && !text.isBlank()) {
            try {
                seconds = Double.parseDouble(text);
            } catch (NumberFormatException error) {
                log.warn("care record details.ts is not a number: '{}'", text);
                return null;
            }
        }
        if (seconds == null) {
            return null;
        }
        long whole = (long) Math.floor(seconds);
        long nanos = Math.round((seconds - whole) * 1_000_000_000L);
        return OffsetDateTime.ofInstant(Instant.ofEpochSecond(whole, nanos), SEOUL);
    }

    private static OffsetDateTime fromLocalDate(Object raw) {
        if (!(raw instanceof String text) || text.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(text).atStartOfDay(SEOUL).toOffsetDateTime();
        } catch (RuntimeException error) {
            log.warn("care record details.metricDate is not a readable date: '{}'", text);
            return null;
        }
    }
}
