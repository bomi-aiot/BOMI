package com.ssafy.bomi.onboarding.application;

import com.ssafy.bomi.fact.application.FactMaterializer;
import com.ssafy.bomi.fact.domain.FactCandidate;
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
 * <h2>What it covers</h2>
 *
 * <p>It materializes every target the onboarding contract can produce today:
 * {@code app_user} (the four consent questions, preferred name, and the other profile
 * fields), and — via the shared {@link FactMaterializer} — {@code memory} and
 * {@code care_record} (S15P11E102-258). The three write the same way a guardian-web
 * confirmation and a robot re-ask (clarification) do, so a value confirmed on any of the
 * three channels lands in the same place with the same {@code source_candidate_id}
 * bookkeeping.</p>
 *
 * <p>{@code care_relationship} (PRIMARY 보호자 돌봄관리 권한 동의) is <b>not</b> written
 * yet — that flow is entangled with PRIMARY coordination and is out of this ticket's
 * scope. Its candidate stays CONFIRMED rather than MATERIALIZED, which is the honest
 * state: the value is agreed, the final row is not created.</p>
 *
 * <p>The gap is visible rather than silent: {@link #materialize} returns false and logs,
 * and the candidate's status shows CONFIRMED in the database.</p>
 */
@Component
public class OnboardingMaterializer {

    private static final Logger log = LoggerFactory.getLogger(OnboardingMaterializer.class);

    private final FactMaterializer factMaterializer;

    public OnboardingMaterializer(FactMaterializer factMaterializer) {
        this.factMaterializer = factMaterializer;
    }

    /**
     * Applies a confirmed value and, on success, advances {@code candidate} to
     * MATERIALIZED.
     *
     * <p>무엇을 하는가 — 대상이 {@code app_user} 면 이 클래스가 직접 필드를 쓰고
     * candidate 를 실체화한다. {@code memory}/{@code care_record} 면 같은 일을
     * {@link FactMaterializer} 에 위임한다 — 가디언웹·재질의 경로와 같은 컴포넌트를
     * 쓰게 하려는 것이다(CLAUDE.md §12, §17.3). {@code care_relationship} 등 아직 쓰기
     * 경로가 없는 대상은 false 를 돌려주고 candidate 는 CONFIRMED 로 남는다.</p>
     *
     * @return true when the value reached its final source and {@code candidate} is now
     *     MATERIALIZED; false when this ticket cannot write that target yet.
     */
    public boolean materialize(QuestionDefinition question, AppUser senior,
        FactCandidate candidate, Map<String, Object> confirmedValue) {

        if (question.materializesIntoAppUser()) {
            applyToAppUser(question, senior, confirmedValue);
            // PROFILE 대상은 app_user 행 자체가 최종 위치라서 별도의 생성된 행 id 가
            // 없다. senior 자신의 id 를 materialized_target_id 로 남긴다.
            candidate.materialize(senior.getId());
            return true;
        }

        String table = question.materialization() == null ? null : question.materialization().table();
        if ("memory".equals(table) || "care_record".equals(table)) {
            // 계약의 recordType(예: MEDICATION_SCHEDULE)을 그대로 쓴다. candidate.factType
            // 을 대신 쓰면(가디언 경로가 하듯) 두 채널의 record_type 이 갈라질 수 있다.
            String recordType = question.materialization().recordType();
            return factMaterializer.materialize(candidate, confirmedValue, recordType).isPresent();
        }

        log.info("onboarding answer {} confirmed but not materialized: target {} has no write "
                + "path yet; the candidate stays CONFIRMED",
            question.code(),
            table == null ? "unknown" : table);
        return false;
    }

    /** app_user 필드 쓰기 — 대상이 PROFILE 인 경우만 여기로 온다. */
    private void applyToAppUser(QuestionDefinition question, AppUser senior,
        Map<String, Object> confirmedValue) {
        String field = question.materialization().field();
        applyField(field, question, senior, confirmedValue);
    }

    private void applyField(String field, QuestionDefinition question, AppUser senior,
        Map<String, Object> confirmedValue) {
        switch (field) {
            case "personalization_consent_status" -> senior.changePersonalizationConsent(consentOf(confirmedValue));
            case "health_data_consent_status" -> senior.changeHealthDataConsent(consentOf(confirmedValue));
            case "schedule_consent_status" -> senior.changeScheduleConsent(consentOf(confirmedValue));
            case "guardian_sharing_consent_status" ->
                senior.changeGuardianSharingConsent(consentOf(confirmedValue));
            case "preferred_name" -> senior.changePreferredName(text(confirmedValue, "preferredName"));
            case "birth_date" -> senior.changeBirthDate(birthDateOf(confirmedValue));
            case "wake_time" -> senior.changeWakeTime(localTimeOf(confirmedValue, "wakeTime"));
            case "sleep_time" -> senior.changeSleepTime(localTimeOf(confirmedValue, "sleepTime"));
            case "chronic_pain_area" -> senior.changeChronicPainArea(text(confirmedValue, "chronicPainArea"));
            case "preferred_hospital" -> senior.changePreferredHospital(text(confirmedValue, "preferredHospital"));
            // 계약에 app_user 필드가 추가됐는데 여기 분기를 안 만든 경우다. 조용히 넘어가면
            // "동의했는데 반영이 안 되는" 상태가 되므로 요란하게 실패한다.
            default -> throw new IllegalStateException(
                "no materialization branch for app_user field " + field
                    + " (question " + question.code() + ")");
        }
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
