package com.ssafy.bomi.occupancy.application;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Picks the one thing worth saying at the door (S15P11E102-226).
 *
 * <p><b>The doorway is where actionable information pays off most.</b> "It's cold, take a
 * coat" is worth more with a hand on the door handle than at any other moment. That is
 * exactly why it is also the moment we are most tempted to say three things — and the
 * senior is already half out (CLAUDE.md §11, §14).</p>
 *
 * <p><b>So: exactly one item, chosen by priority.</b> Not the most items that fit.</p>
 *
 * <pre>
 *   OUT (배웅)   weather as an action  →  unconfirmed medication  →  today's schedule
 *   IN  (환영)   water  →  check-in  →  rest, if they were out a long time
 * </pre>
 *
 * <p><b>Why the backend decides.</b> Every candidate depends on data only the server has:
 * today's schedule, which doses are still unconfirmed, consent state. Choosing on the robot
 * would put the same priority rule in two places, and then "why didn't it mention the
 * umbrella?" has two possible answers (CLAUDE.md §11).</p>
 */
@Component
public class GreetingDecider {

    private static final Logger log = LoggerFactory.getLogger(GreetingDecider.class);

    private static final String MEDICATION_SCHEDULE = "MEDICATION_SCHEDULE";
    private static final String MEDICATION_TAKEN = "MEDICATION_TAKEN";
    private static final List<String> SCHEDULE_TYPES = List.of("APPOINTMENT", "PERSONAL_SCHEDULE");

    /** 오래 나가 계셨다고 볼 기준. 이보다 짧으면 휴식을 권하지 않는다. */
    private static final Duration LONG_OUTING = Duration.ofHours(3);

    private final CareRecordRepository careRecordRepository;

    public GreetingDecider(CareRecordRepository careRecordRepository) {
        this.careRecordRepository = careRecordRepository;
    }

    /**
     * Decides what to say, or that nothing should be said.
     *
     * @param awaySince when the senior left, for an {@code IN} passage. Null when unknown
     * @return the single sentence, or empty when the robot should stay quiet
     */
    public Optional<String> decide(UUID seniorId, OccupancyDirection direction,
        OffsetDateTime awaySince, OffsetDateTime now) {

        return direction == OccupancyDirection.OUT
            ? escort(seniorId, now)
            : welcome(awaySince, now);
    }

    /**
     * On the way out, in priority order.
     *
     * <p><b>Weather is missing and that is a real gap, not a simplification.</b> §11 puts it
     * first — "it's raining, take an umbrella" is the highest-value thing to say at the
     * door. The backend has no weather source today (the robot's `weather/client.py` is on
     * the other side of the boundary), so the chain currently starts at medication.
     * Documented in PROGRESS rather than faked.</p>
     */
    private Optional<String> escort(UUID seniorId, OffsetDateTime now) {
        // 1순위: 날씨. → 미구현. 백엔드에 날씨 출처가 없다.

        // 2순위: 아직 확인되지 않은 복약.
        //
        // 나가시기 전이 마지막 기회다. 돌아오신 뒤에 묻는 것은 이미 늦은 경우가 많다.
        Optional<String> medication = unconfirmedMedication(seniorId, now);
        if (medication.isPresent()) {
            return medication;
        }

        // 3순위: 오늘 일정. 나가는 김에 들르실 수 있다.
        Optional<String> appointment = todaysAppointment(seniorId, now);
        if (appointment.isPresent()) {
            return appointment;
        }

        return Optional.of("다녀오세요. 조심히 다녀오세요.");
    }

    /**
     * On the way back.
     *
     * <p>Water first: dehydration is one of the things seniors notice least and it costs
     * nothing to mention. Rest only when they were actually out a long time — saying it
     * after a ten-minute errand sounds like the robot was not paying attention.</p>
     */
    private Optional<String> welcome(OffsetDateTime awaySince, OffsetDateTime now) {
        if (awaySince != null && Duration.between(awaySince, now).compareTo(LONG_OUTING) >= 0) {
            return Optional.of("오래 걸으셨네요. 좀 쉬시는 게 어떠세요?");
        }
        return Optional.of("어서 오세요. 물 한 잔 드시겠어요?");
    }

    /**
     * A dose scheduled for today with no matching taken-record.
     *
     * <p>Reads {@code details.scheduledAt} because {@code care_record} has no timestamp
     * column — the convention S15P11E102-224 established, and the reason 230 exists. Using
     * a second convention here would give the dashboard and the greeting different answers
     * about the same dose.</p>
     */
    private Optional<String> unconfirmedMedication(UUID seniorId, OffsetDateTime now) {
        List<CareRecord> records = careRecordRepository
            .findBySeniorIdAndStatus(seniorId, CareRecordStatus.ACTIVE);

        boolean anyTakenToday = records.stream()
            .filter(record -> MEDICATION_TAKEN.equals(record.getRecordType()))
            .anyMatch(record -> isToday(record, now));
        if (anyTakenToday) {
            return Optional.empty();
        }

        boolean hasSchedule = records.stream()
            .anyMatch(record -> MEDICATION_SCHEDULE.equals(record.getRecordType()));
        if (!hasSchedule) {
            return Optional.empty();
        }

        // 약 이름을 말하지 않는다. 현관에서 듣는 한 문장에 정보를 두 개 담으면 둘 다
        // 남지 않고, 어느 약인지는 어르신이 이미 아신다 (CLAUDE.md §14).
        return Optional.of("나가시기 전에 약은 드셨어요?");
    }

    private Optional<String> todaysAppointment(UUID seniorId, OffsetDateTime now) {
        return careRecordRepository
            .findBySeniorIdAndStatusAndRecordTypeIn(seniorId, CareRecordStatus.ACTIVE, SCHEDULE_TYPES)
            .stream()
            .filter(record -> isToday(record, now))
            .findFirst()
            .map(record -> "오늘 약속이 있으셨죠. 잊지 마세요.");
    }

    private boolean isToday(CareRecord record, OffsetDateTime now) {
        Object raw = record.getDetails() == null ? null : record.getDetails().get("scheduledAt");
        if (!(raw instanceof String text) || text.isBlank()) {
            return false;
        }
        try {
            return OffsetDateTime.parse(text).toLocalDate().equals(now.toLocalDate());
        } catch (RuntimeException error) {
            log.debug("care record {} has an unparseable scheduledAt; not counting it",
                record.getId());
            return false;
        }
    }
}
