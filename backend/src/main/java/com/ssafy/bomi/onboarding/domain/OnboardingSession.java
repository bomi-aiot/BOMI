package com.ssafy.bomi.onboarding.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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
 * App/robot-shared onboarding session for a senior (maps table
 * {@code onboarding_session}).
 *
 * <p>Aggregate root. {@code senior_id} and {@code robot_id} are raw {@link UUID}
 * logical references (no physical FK). App-started sessions may have a null
 * {@code robot_id}; robot-started sessions require it (§5). {@code startedChannel}
 * is the first channel, and both channels may continue the same
 * {@code IN_PROGRESS} session. The session status and
 * {@code app_user.onboarding_status} are updated in the same transaction.</p>
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

    /** Nullable for app-started sessions; required for robot-started sessions (§5). */
    @Column(name = "robot_id")
    private UUID robotId;

    @Column(name = "question_set_version", length = 50)
    private String questionSetVersion;

    @Enumerated(EnumType.STRING)
    @Column(name = "started_channel", nullable = false, length = 30)
    private OnboardingChannel startedChannel;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private OnboardingSessionStatus status = OnboardingSessionStatus.IN_PROGRESS;

    @Column(name = "current_question_code", length = 100)
    private String currentQuestionCode;

    @Column(name = "started_at", nullable = false)
    private OffsetDateTime startedAt;

    @Column(name = "completed_at")
    private OffsetDateTime completedAt;

    @Column(name = "ended_at")
    private OffsetDateTime endedAt;

    private OnboardingSession(UUID seniorId, UUID robotId, OnboardingChannel startedChannel,
        String questionSetVersion) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.startedChannel = requireNonNull(startedChannel, "startedChannel");
        if (startedChannel == OnboardingChannel.ROBOT && robotId == null) {
            throw new IllegalArgumentException("robotId is required for a ROBOT-started session");
        }
        this.robotId = robotId;
        this.questionSetVersion = questionSetVersion;
        this.startedAt = OffsetDateTime.now();
    }

    /** Starts a session on the app channel (robot optional). */
    public static OnboardingSession startFromApp(UUID seniorId, UUID robotId, String questionSetVersion) {
        return new OnboardingSession(seniorId, robotId, OnboardingChannel.APP, questionSetVersion);
    }

    /** Starts a session on the robot channel (robot required). */
    public static OnboardingSession startFromRobot(UUID seniorId, UUID robotId, String questionSetVersion) {
        return new OnboardingSession(seniorId, robotId, OnboardingChannel.ROBOT, questionSetVersion);
    }

    public void moveToQuestion(String questionCode) {
        this.currentQuestionCode = questionCode;
    }

    public void changeStatus(OnboardingSessionStatus status) {
        this.status = requireNonNull(status, "status");
    }

    public void complete() {
        this.status = OnboardingSessionStatus.COMPLETED;
        this.completedAt = OffsetDateTime.now();
        this.endedAt = this.completedAt;
    }

    public void end(OnboardingSessionStatus terminalStatus) {
        this.status = requireNonNull(terminalStatus, "terminalStatus");
        this.endedAt = OffsetDateTime.now();
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
