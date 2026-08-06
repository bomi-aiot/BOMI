package com.ssafy.bomi.care.application;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordTime;
import com.ssafy.bomi.care.domain.NotificationTier;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.domain.RelationshipStatus;
import com.ssafy.bomi.relationship.repository.CareRelationshipRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Where the robot's outbound queue lands (S15P11E102-211).
 *
 * <p><b>Why the robot does not talk to a push service directly.</b> Credentials on the
 * robot mean push tokens shipped to every device, and one stolen robot takes those tokens
 * with it. The robot forwards; the server reaches the guardian.</p>
 *
 * <p><b>T1 ignores consent. T2 and T3 do not.</b> That asymmetry is a deliberate product
 * decision, not an oversight: life-safety alerts go out regardless of
 * {@code guardian_sharing_consent_status}, and the consent copy has to say so plainly, or
 * a family discovers it at the worst possible moment (CLAUDE.md §9).</p>
 *
 * <p><b>Refusal is not failure.</b> When consent is missing the response says so instead
 * of erroring. A robot that cannot tell "the server refused" from "the network is down"
 * retries forever, and every retry is a wasted radio wake-up on a battery.</p>
 */
@Service
public class GuardianAlertService {

    private static final Logger log = LoggerFactory.getLogger(GuardianAlertService.class);

    /** Care-record type for anything the robot escalated. Distinct from schedules. */
    private static final String ALERT_RECORD_TYPE = "GUARDIAN_ALERT";

    private final CareRecordRepository careRecordRepository;
    private final CareRelationshipRepository relationshipRepository;
    private final AppUserRepository appUserRepository;

    public GuardianAlertService(CareRecordRepository careRecordRepository,
        CareRelationshipRepository relationshipRepository,
        AppUserRepository appUserRepository) {
        this.careRecordRepository = careRecordRepository;
        this.relationshipRepository = relationshipRepository;
        this.appUserRepository = appUserRepository;
    }

    /**
     * Accepts one alert from the robot.
     *
     * @param payload what the robot observed. Aggregates and reasons only — the robot does
     *     not send the senior's words, and this service does not add them
     * @return whether it will reach the guardian, and why not when it will not
     */
    @Transactional
    public AlertOutcome accept(UUID seniorId, NotificationTier tier, Map<String, Object> payload) {
        if (tier != NotificationTier.T1 && !hasSharingConsent(seniorId)) {
            // Recorded but not delivered. Dropping it entirely would lose the observation;
            // delivering it would share what the senior did not agree to share.
            CareRecord withheld = save(seniorId, tier, payload, null);
            log.info("withholding a {} alert for senior {}: sharing consent not granted",
                tier, seniorId);
            return new AlertOutcome(withheld.getId(), false, "CONSENT_NOT_GRANTED");
        }

        Optional<UUID> guardianId = primaryGuardian(seniorId);
        CareRecord record = save(seniorId, tier, payload, guardianId.orElse(null));

        if (guardianId.isEmpty()) {
            // A senior mid-onboarding has no guardian yet. The alert is kept so it appears
            // the moment somebody connects, rather than vanishing into a 500.
            log.warn("no primary guardian for senior {}; the {} alert is recorded but has "
                + "nobody to reach", seniorId, tier);
            return new AlertOutcome(record.getId(), false, "NO_GUARDIAN");
        }

        if (tier == NotificationTier.T1) {
            log.warn("T1 alert accepted for senior {} (reason={})", seniorId,
                payload.getOrDefault("reason", "unspecified"));
        }
        return new AlertOutcome(record.getId(), true, null);
    }

    private CareRecord save(UUID seniorId, NotificationTier tier, Map<String, Object> payload,
        UUID recipientGuardianId) {
        CareRecord record = CareRecord.create(seniorId, ALERT_RECORD_TYPE, payload);
        record.markAsNotification(tier, recipientGuardianId);
        // 알림이 '일어난' 시각 (S15P11E102-230).
        //
        // 로봇의 발신 큐가 payload.ts 를 싣는데, 그 값이 중요하다. 네트워크가 끊긴 동안
        // 큐에 쌓였다가 한참 뒤에 도착하는 알림이 있고, 그때 도착 시각으로 적으면
        // "새벽 3시에 반응이 없었다"가 아침 알림으로 보인다. 로봇이 관찰한 시각이 진실이다.
        // 그 값이 없을 때만 지금으로 둔다 — 이 경우는 방금 일어난 일이 맞다.
        record.occurredAt(CareRecordTime.fromDetailsOrNow(payload, OffsetDateTime.now()));
        return careRecordRepository.save(record);
    }

    /**
     * Whether the senior agreed to share with their guardian.
     *
     * <p>A missing user is treated as no consent. Guessing the other way would share on
     * behalf of somebody the system cannot even find.</p>
     */
    private boolean hasSharingConsent(UUID seniorId) {
        return appUserRepository.findById(seniorId)
            .map(AppUser::getGuardianSharingConsentStatus)
            .filter(status -> status == ConsentStatus.GRANTED)
            .isPresent();
    }

    private Optional<UUID> primaryGuardian(UUID seniorId) {
        return relationshipRepository
            .findFirstBySeniorIdAndPriorityAndStatus(
                seniorId, RelationshipPriority.PRIMARY, RelationshipStatus.ACTIVE)
            .map(CareRelationship::getGuardianId);
    }

    /**
     * What happened to one alert.
     *
     * @param delivered false when the server accepted the alert but will not pass it on
     * @param reason why not, or {@code null} when it will be delivered. The robot logs this
     *     and stops retrying — a refusal is not a network failure
     */
    public record AlertOutcome(UUID careRecordId, boolean delivered, String reason) {
    }
}
