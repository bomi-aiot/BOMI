package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.fact.domain.FactTargetDomain;
import java.util.Set;

/**
 * 사실 후보 하나가 사람 확인 없이 곧장 memory/care_record 로 실체화돼도 되는지
 * 판정한다 (S15P11E102-255).
 *
 * <p>왜 존재하는가 — {@code ConversationFactIntakeService} 는 지금까지 CAPTURED
 * 상태로 큐에 쌓기만 하고 아무 판단도 하지 않았다. "요즘 손자가 놀러 온다" 같은
 * 안전한 이야기와 "이제 아침 약 안 먹어" 같은 위험한 변경을 똑같이 취급하면,
 * 후자가 확인 없이 memory/care_record 에 조용히 반영될 수 있다 — 실제 복약과
 * 다른 정보가 돌봄기록에 남는 것은 이 제품에서 가장 위험한 실패 축이다
 * (CLAUDE.md §8 쓰기 경로 안전 규칙).</p>
 *
 * <p>판정 어휘 — {@code ConversationContextService} 의 {@code HEALTH_RECORD_TYPES}/
 * {@code SCHEDULE_RECORD_TYPES} 와 같은 값을 그대로 따른다. 채널마다 같은 사실을
 * 다른 이름으로 분류하면 나중에 대조가 안 된다 — S15P11E102-258 이 조사 중 발견한
 * 것과 같은 종류의 결함이다.</p>
 */
final class FactRiskPolicy {

    /** 복약·알레르기·질환 — 잘못 반영되면 돌봄에 직접 영향을 준다. 절대 자동 반영하지 않는다. */
    private static final Set<String> HEALTH_FACT_TYPES =
            Set.of("MEDICATION", "MEDICATION_SCHEDULE", "ALLERGY", "HEALTH_CONDITION");

    /** 일정류 — 확인 없이 반영돼도 되돌리기 쉽다(달력 수정 정도). */
    private static final Set<String> SCHEDULE_FACT_TYPES = Set.of("APPOINTMENT", "PERSONAL_SCHEDULE");

    private FactRiskPolicy() {
    }

    static boolean requiresHealthConsent(String factType) {
        return HEALTH_FACT_TYPES.contains(factType);
    }

    static boolean requiresScheduleConsent(String factType) {
        return SCHEDULE_FACT_TYPES.contains(factType);
    }

    /**
     * 사람 확인(재질의·가디언웹) 없이 곧장 실체화해도 되는가.
     *
     * <p>MEMORY 는 항상 안전하다 — {@link FactMaterializer} 가 항상 PRIVATE(본인만
     * 보기)로만 저장하고, 틀려도 대화 소재 하나가 어긋나는 정도다. CARE_RECORD 는
     * 일정류({@code SCHEDULE_FACT_TYPES})만 안전하다고 본다 — 건강·복약
     * ({@code HEALTH_FACT_TYPES})은 물론, 이 목록에 없는 낯선 factType 도 기본값은
     * "확인 필요"다. 모르는 것을 안전하다고 가정하지 않는다(CLAUDE.md §9 의
     * "확실치 않으면 보수적으로"와 같은 원칙). PROFILE/CARE_RELATIONSHIP 은 애초에
     * 이 판정까지 오지 않는다 — {@code ConversationFactIntakeService} 가 입구에서
     * 400 으로 거절한다.</p>
     */
    static boolean isSafeForAutoMaterialization(FactTargetDomain domain, String factType) {
        if (domain == FactTargetDomain.MEMORY) {
            return true;
        }
        if (domain == FactTargetDomain.CARE_RECORD) {
            return SCHEDULE_FACT_TYPES.contains(factType);
        }
        return false;
    }
}
