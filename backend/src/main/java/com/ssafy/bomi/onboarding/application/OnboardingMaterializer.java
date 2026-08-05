package com.ssafy.bomi.onboarding.application;

import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeParseException;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Writes a confirmed onboarding value into its final source.
 *
 * <p>Only a confirmed value may be materialized (design note §1, MVP ERD §6). This
 * class is deliberately the single place that write happens, so "what did onboarding
 * actually change" is answerable by reading one file.</p>
 *
 * <h2>What it covers today, and what it does not</h2>
 *
 * <p>It materializes the {@code app_user} targets — the four consent questions and the
 * preferred name. That is every <b>required</b> question in the contract, and it is also
 * what the rest of the flow depends on: consent gates every later question, so leaving it
 * unwritten would stall onboarding at the first medication prompt.</p>
 *
 * <p>{@code memory}, {@code care_record} and {@code care_relationship} targets are
 * <b>not</b> written yet. Those candidates stay CONFIRMED rather than MATERIALIZED, which
 * is the honest state: the value is agreed, the final row is not created. They need their
 * own write paths (idempotency, {@code source_candidate_id} uniqueness, PRIMARY
 * coordination for the guardian one) and that is more than an API ticket.</p>
 *
 * <p>The gap is visible rather than silent: {@link #materialize} returns false and logs,
 * and the candidate's status shows CONFIRMED in the database.</p>
 */
@Component
public class OnboardingMaterializer {

    private static final Logger log = LoggerFactory.getLogger(OnboardingMaterializer.class);

    /**
     * Applies a confirmed value.
     *
     * @return true when the value reached its final source; false when this ticket
     *     cannot write that target yet.
     */
    public boolean materialize(QuestionDefinition question, AppUser senior,
        Map<String, Object> confirmedValue) {

        if (!question.materializesIntoAppUser()) {
            log.info("onboarding answer {} confirmed but not materialized: target {} has no write "
                    + "path yet; the candidate stays CONFIRMED",
                question.code(),
                question.materialization() == null ? "unknown" : question.materialization().table());
            return false;
        }

        String field = question.materialization().field();
        return switch (field) {
            case "personalization_consent_status" -> {
                senior.changePersonalizationConsent(consentOf(confirmedValue));
                yield true;
            }
            case "health_data_consent_status" -> {
                senior.changeHealthDataConsent(consentOf(confirmedValue));
                yield true;
            }
            case "schedule_consent_status" -> {
                senior.changeScheduleConsent(consentOf(confirmedValue));
                yield true;
            }
            case "guardian_sharing_consent_status" -> {
                senior.changeGuardianSharingConsent(consentOf(confirmedValue));
                yield true;
            }
            case "preferred_name" -> {
                senior.changePreferredName(text(confirmedValue, "preferredName"));
                yield true;
            }
            case "birth_date" -> {
                senior.changeBirthDate(birthDateOf(confirmedValue));
                yield true;
            }
            case "wake_time" -> {
                senior.changeWakeTime(localTimeOf(confirmedValue, "wakeTime"));
                yield true;
            }
            case "sleep_time" -> {
                senior.changeSleepTime(localTimeOf(confirmedValue, "sleepTime"));
                yield true;
            }
            case "chronic_pain_area" -> {
                senior.changeChronicPainArea(text(confirmedValue, "chronicPainArea"));
                yield true;
            }
            case "preferred_hospital" -> {
                senior.changePreferredHospital(text(confirmedValue, "preferredHospital"));
                yield true;
            }
            // 계약에 app_user 필드가 추가됐는데 여기 분기를 안 만든 경우다. 조용히 넘어가면
            // "동의했는데 반영이 안 되는" 상태가 되므로 요란하게 실패한다.
            default -> throw new IllegalStateException(
                "no materialization branch for app_user field " + field
                    + " (question " + question.code() + ")");
        };
    }

    /**
     * Reads the consent decision from the confirmed value.
     *
     * <p>The contract's schema allows GRANTED or DENIED only. Anything else means the
     * robot sent something the schema should have rejected, and treating an unknown
     * value as "granted" is exactly the mistake that must never happen with consent.</p>
     */
    private ConsentStatus consentOf(Map<String, Object> confirmedValue) {
        String raw = text(confirmedValue, "consentStatus");
        ConsentStatus status = switch (raw) {
            case "GRANTED" -> ConsentStatus.GRANTED;
            case "DENIED" -> ConsentStatus.DENIED;
            default -> throw new IllegalArgumentException(
                "consentStatus must be GRANTED or DENIED, got " + raw);
        };
        return status;
    }

    /**
     * 확정된 생년월일 문자열(ISO-8601, "YYYY-MM-DD")을 {@link LocalDate} 로 바꾼다.
     *
     * <p>스키마 검증(answerSchema.birthDate.format = date)이 형식을 이미 걸러내는 것이
     * 원칙이지만, 여기서도 다시 파싱을 검증한다 — ASR 을 거친 값이 스키마를 통과했다고
     * 항상 파싱 가능하다고 믿으면, 잘못된 값이 조용히 예외로 죽는 대신 엉뚱한 나이로
     * 계산돼 버릴 수 있다.</p>
     */
    private LocalDate birthDateOf(Map<String, Object> confirmedValue) {
        String raw = text(confirmedValue, "birthDate");
        try {
            return LocalDate.parse(raw);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException("birthDate must be ISO-8601 (YYYY-MM-DD), got " + raw);
        }
    }

    /**
     * 확정된 시각 문자열("HH:mm")을 {@link LocalTime} 으로 바꾼다.
     *
     * <p>birthDateOf 와 같은 이유로 여기서도 다시 검증한다 — 스키마 검증을 통과했다고
     * 항상 파싱 가능하다고 믿으면, ASR 을 거친 값이 조용히 예외로 죽는 대신 엉뚱한
     * 시각으로 저장될 수 있다.</p>
     */
    private LocalTime localTimeOf(Map<String, Object> confirmedValue, String field) {
        String raw = text(confirmedValue, field);
        try {
            return LocalTime.parse(raw);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException(field + " must be HH:mm, got " + raw);
        }
    }

    private String text(Map<String, Object> value, String field) {
        Object raw = Optional.ofNullable(value).map(v -> v.get(field)).orElse(null);
        if (raw == null || raw.toString().isBlank()) {
            throw new IllegalArgumentException("confirmed value is missing " + field);
        }
        return raw.toString();
    }
}
