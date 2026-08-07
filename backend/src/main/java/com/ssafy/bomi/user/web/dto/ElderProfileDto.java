package com.ssafy.bomi.user.web.dto;

import java.util.Map;

/**
 * 어르신 프로필 조회 DTO (기본정보). app_user 컬럼을 그대로 미러링한다.
 * 표시값 변환은 FE 매퍼가 담당(계약퍼스트).
 *
 * <p>주의: 건강정보(질환·알레르기 등)와 성별·전화는 app_user 스키마에 없어 포함하지 않는다.
 * 자택 주소(home_address)는 S15P11E102-347 로 app_user 에 추가됐지만, 이 DTO 는 노출하지
 * 않는다 — 로봇 대화 문맥 채널(SeniorProfile.address) 전용이다(개인정보 범위 결정).
 * 생년월일(birth_date)은 S15P11E102-259 로 app_user 에 추가됐지만, 이 DTO 는 아직 노출하지
 * 않는다 — 대화 문맥(ConversationContextResponse.SeniorProfile)만 나이로 계산해 싣는다.
 * {@code conversationPreferences} 는 jsonb 원본(예: speechRate/volume/repeatWhenUnclear).</p>
 */
public record ElderProfileDto(
        String id,
        String userType,
        String name,
        String preferredName,
        String onboardingStatus,
        String timeZone,
        String status,
        String personalizationConsentStatus,
        String healthDataConsentStatus,
        String scheduleConsentStatus,
        String guardianSharingConsentStatus,
        Map<String, Object> conversationPreferences,
        String createdAt,
        String updatedAt) {
}
