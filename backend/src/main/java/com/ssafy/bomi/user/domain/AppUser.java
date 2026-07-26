package com.ssafy.bomi.user.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/**
 * Application user (maps table {@code app_user}).
 *
 * <p>Aggregate root. {@code user_type} is kept as a raw {@link String} because the
 * SQL neither enumerates allowed values nor provides a default; it can become an
 * enum once the ERD confirms the value set.</p>
 */
@Entity
@Table(name = "app_user")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "user_type", nullable = false, length = 30)
    private String userType;

    @Column(name = "name", nullable = false, length = 100)
    private String name;

    @Column(name = "email", length = 255)
    private String email;

    @Column(name = "preferred_name", length = 100)
    private String preferredName;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "conversation_preferences", nullable = false)
    private Map<String, Object> conversationPreferences = new HashMap<>();

    @Enumerated(EnumType.STRING)
    @Column(name = "onboarding_status", nullable = false, length = 30)
    private OnboardingStatus onboardingStatus = OnboardingStatus.NOT_STARTED;

    @Column(name = "time_zone", nullable = false, length = 50)
    private String timeZone = "Asia/Seoul";

    @Enumerated(EnumType.STRING)
    @Column(name = "personalization_consent_status", nullable = false, length = 30)
    private ConsentStatus personalizationConsentStatus = ConsentStatus.NOT_REQUESTED;

    @Enumerated(EnumType.STRING)
    @Column(name = "health_data_consent_status", nullable = false, length = 30)
    private ConsentStatus healthDataConsentStatus = ConsentStatus.NOT_REQUESTED;

    @Enumerated(EnumType.STRING)
    @Column(name = "schedule_consent_status", nullable = false, length = 30)
    private ConsentStatus scheduleConsentStatus = ConsentStatus.NOT_REQUESTED;

    @Enumerated(EnumType.STRING)
    @Column(name = "guardian_sharing_consent_status", nullable = false, length = 30)
    private ConsentStatus guardianSharingConsentStatus = ConsentStatus.NOT_REQUESTED;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private UserStatus status = UserStatus.ACTIVE;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    private AppUser(String userType, String name, String email, String preferredName) {
        this.userType = requireText(userType, "userType");
        this.name = requireText(name, "name");
        this.email = email;
        this.preferredName = preferredName;
    }

    /** Creates a user with the mandatory columns only. */
    public static AppUser create(String userType, String name) {
        return new AppUser(userType, name, null, null);
    }

    /** Creates a user including the optional contact columns. */
    public static AppUser create(String userType, String name, String email, String preferredName) {
        return new AppUser(userType, name, email, preferredName);
    }

    public void updateProfile(String name, String preferredName) {
        this.name = requireText(name, "name");
        this.preferredName = preferredName;
    }

    public void changeEmail(String email) {
        this.email = email;
    }

    public void changeTimeZone(String timeZone) {
        this.timeZone = requireText(timeZone, "timeZone");
    }

    public void changeOnboardingStatus(OnboardingStatus onboardingStatus) {
        this.onboardingStatus = requireNonNull(onboardingStatus, "onboardingStatus");
    }

    public void changePersonalizationConsent(ConsentStatus status) {
        this.personalizationConsentStatus = requireNonNull(status, "personalizationConsentStatus");
    }

    public void changeHealthDataConsent(ConsentStatus status) {
        this.healthDataConsentStatus = requireNonNull(status, "healthDataConsentStatus");
    }

    public void changeScheduleConsent(ConsentStatus status) {
        this.scheduleConsentStatus = requireNonNull(status, "scheduleConsentStatus");
    }

    public void changeGuardianSharingConsent(ConsentStatus status) {
        this.guardianSharingConsentStatus = requireNonNull(status, "guardianSharingConsentStatus");
    }

    public void changeStatus(UserStatus status) {
        this.status = requireNonNull(status, "status");
    }

    public void updateConversationPreferences(Map<String, Object> preferences) {
        this.conversationPreferences = preferences == null ? new HashMap<>() : new HashMap<>(preferences);
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
