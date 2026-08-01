package com.ssafy.bomi.user.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalTime;
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

    /**
     * Start of the senior's quiet hours, in <em>local</em> time.
     *
     * <p>Read by the proactive gate on every tick and shared with the silence
     * ladder: quiet at 4 a.m. is not a warning sign, it is sleep.</p>
     *
     * <p>Interpret with {@link #timeZone}, never as UTC. The window normally crosses
     * midnight (22:00–07:00), so {@code start > end} is the expected case and a
     * naive {@code start <= now && now <= end} comparison is wrong exactly when it
     * matters most.</p>
     *
     * <p>Not null, with a default, because null would mean "no quiet window" — the
     * robot free to talk at 3 a.m. For a care device the safe default is to have one.</p>
     */
    @Column(name = "quiet_hours_start", nullable = false)
    private LocalTime quietHoursStart = LocalTime.of(22, 0);

    /** End of quiet hours, local time. See {@link #quietHoursStart}. */
    @Column(name = "quiet_hours_end", nullable = false)
    private LocalTime quietHoursEnd = LocalTime.of(7, 0);

    /**
     * Home coordinates, the reference point for nearby clinic and pharmacy lookup.
     *
     * <p>Nullable: not every senior has them set, and that feature degrading is
     * acceptable where a wrong location would not be. {@code numeric(9,6)} holds the
     * full latitude/longitude range at roughly 0.1 m resolution.</p>
     */
    @Column(name = "home_latitude", precision = 9, scale = 6)
    private BigDecimal homeLatitude;

    @Column(name = "home_longitude", precision = 9, scale = 6)
    private BigDecimal homeLongitude;

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

    /**
     * Sets the quiet-hours window in the senior's local time.
     *
     * <p>Equal start and end is rejected: it reads as either a zero-length window or
     * a 24-hour one depending on the comparison, and the gate must never have to
     * guess which. To disable quiet hours, widen the window instead.</p>
     */
    public void changeQuietHours(LocalTime start, LocalTime end) {
        requireNonNull(start, "quietHoursStart");
        requireNonNull(end, "quietHoursEnd");
        if (start.equals(end)) {
            throw new IllegalArgumentException("quiet hours start and end must differ");
        }
        this.quietHoursStart = start;
        this.quietHoursEnd = end;
    }

    /** Sets or clears the home coordinates used for nearby clinic and pharmacy lookup. */
    public void changeHomeCoordinates(BigDecimal latitude, BigDecimal longitude) {
        if ((latitude == null) != (longitude == null)) {
            throw new IllegalArgumentException("latitude and longitude must be set together");
        }
        this.homeLatitude = latitude;
        this.homeLongitude = longitude;
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
