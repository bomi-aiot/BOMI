package com.ssafy.bomi.occupancy.application;

import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
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
     * <p>"Any dose today" is a range query on {@code occurred_at} (S15P11E102-230). It used
     * to parse {@code details.scheduledAt} out of every active record, because
     * {@code care_record} had no timestamp column.</p>
     */
    private Optional<String> unconfirmedMedication(UUID seniorId, OffsetDateTime now) {
        boolean anyTakenToday = !careRecordRepository.findByTypesBetween(
            seniorId, CareRecordStatus.ACTIVE, List.of(MEDICATION_TAKEN),
            startOfDay(now), startOfNextDay(now)).isEmpty();
        if (anyTakenToday) {
            return Optional.empty();
        }

        boolean hasSchedule = !careRecordRepository
            .findBySeniorIdAndStatusAndRecordTypeIn(
                seniorId, CareRecordStatus.ACTIVE, List.of(MEDICATION_SCHEDULE))
            .isEmpty();
        if (!hasSchedule) {
            // 반복 스케줄은 occurred_at 이 없다(시간축의 한 점이 아니다). 그래서 여기만
            // 범위 질의가 아니라 존재 확인이다 — 범위를 걸면 항상 0건이 나온다.
            return Optional.empty();
        }

        // 약 이름을 말하지 않는다. 현관에서 듣는 한 문장에 정보를 두 개 담으면 둘 다
        // 남지 않고, 어느 약인지는 어르신이 이미 아신다 (CLAUDE.md §14).
        return Optional.of("나가시기 전에 약은 드셨어요?");
    }

    /**
     * Today's appointment, if there is one.
     *
     * <p><b>This never fired before S15P11E102-230.</b> It looked for
     * {@code details.scheduledAt}, and the write path
     * ({@code CareRecordCommandService.createSchedule}) stores {@code startsAt}. Two
     * conventions for the same idea, and nothing in the schema forced them to agree, so the
     * mismatch stayed silent — the greeting simply fell through to "다녀오세요" every time.
     * Both now feed one column.</p>
     */
    private Optional<String> todaysAppointment(UUID seniorId, OffsetDateTime now) {
        return careRecordRepository.findByTypesBetween(
                seniorId, CareRecordStatus.ACTIVE, SCHEDULE_TYPES,
                startOfDay(now), startOfNextDay(now))
            .stream()
            .findFirst()
            .map(record -> "오늘 약속이 있으셨죠. 잊지 마세요.");
    }

    /**
     * The day boundary, taken from the offset of {@code now}.
     *
     * <p>The caller's {@code now} carries the senior's offset, so "today" means their
     * today. Using UTC here would ask about yesterday's appointments for anyone who goes
     * out before 09:00 Korean time.</p>
     */
    private static OffsetDateTime startOfDay(OffsetDateTime now) {
        return now.toLocalDate().atStartOfDay().atOffset(now.getOffset());
    }

    private static OffsetDateTime startOfNextDay(OffsetDateTime now) {
        return startOfDay(now).plusDays(1);
    }
}
