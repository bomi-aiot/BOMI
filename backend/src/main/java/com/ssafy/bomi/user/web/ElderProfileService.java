package com.ssafy.bomi.user.web;

import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import com.ssafy.bomi.user.web.dto.ElderProfileDto;
import java.time.OffsetDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 어르신 프로필(기본정보) 조회 서비스. 단일 어르신 전제(P0). */
@Service
public class ElderProfileService {

    private static final String SENIOR_USER_TYPE = "SENIOR";

    private final AppUserRepository appUserRepository;

    public ElderProfileService(AppUserRepository appUserRepository) {
        this.appUserRepository = appUserRepository;
    }

    @Transactional(readOnly = true)
    public ElderProfileDto getProfile() {
        AppUser senior = appUserRepository.findFirstByUserType(SENIOR_USER_TYPE)
                .orElseThrow(() -> new IllegalStateException("등록된 어르신이 없습니다."));
        return new ElderProfileDto(
                senior.getId().toString(),
                senior.getUserType(),
                senior.getName(),
                senior.getPreferredName(),
                name(senior.getOnboardingStatus()),
                senior.getTimeZone(),
                name(senior.getStatus()),
                name(senior.getPersonalizationConsentStatus()),
                name(senior.getHealthDataConsentStatus()),
                name(senior.getScheduleConsentStatus()),
                name(senior.getGuardianSharingConsentStatus()),
                senior.getConversationPreferences(),
                iso(senior.getCreatedAt()),
                iso(senior.getUpdatedAt()));
    }

    private static String name(Enum<?> value) {
        return value == null ? null : value.name();
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
