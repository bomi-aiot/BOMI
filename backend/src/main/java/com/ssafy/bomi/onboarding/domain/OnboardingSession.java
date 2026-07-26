package com.ssafy.bomi.onboarding.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Onboarding session for a senior and robot (maps table
 * {@code onboarding_session}).
 *
 * <p>Aggregate root. {@code senior_id} and {@code robot_id} are raw {@link UUID}
 * logical references; the SQL declares no foreign key. The related
 * {@code onboarding_answer} table is intentionally out of scope (Conversation
 * redesign).</p>
 */
@Entity
@Table(name = "onboarding_session")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class OnboardingSession {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "robot_id", nullable = false)
    private UUID robotId;

    @Column(name = "current_question_code", length = 100)
    private String currentQuestionCode;

    @Column(name = "started_at", nullable = false)
    private OffsetDateTime startedAt;

    @Column(name = "completed_at")
    private OffsetDateTime completedAt;

    @Column(name = "ended_at")
    private OffsetDateTime endedAt;

    private OnboardingSession(UUID seniorId, UUID robotId) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.robotId = requireNonNull(robotId, "robotId");
        this.startedAt = OffsetDateTime.now();
    }

    public static OnboardingSession create(UUID seniorId, UUID robotId) {
        return new OnboardingSession(seniorId, robotId);
    }

    public void moveToQuestion(String questionCode) {
        this.currentQuestionCode = questionCode;
    }

    public void complete() {
        this.completedAt = OffsetDateTime.now();
    }

    public void end() {
        this.endedAt = OffsetDateTime.now();
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
