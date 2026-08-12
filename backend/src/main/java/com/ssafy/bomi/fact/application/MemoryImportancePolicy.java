package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.memory.domain.MemoryType;
import java.util.Map;

/**
 * 새로 만들어지는 기억의 중요도를 정한다 (2026-08-10).
 *
 * <p>왜 존재하는가 — {@code ConversationContextService.score} 는
 * {@code similarity × (importance/5) × recency × usagePenalty} 로 기억을 고른다.
 * 그런데 이 값을 채우는 프로덕션 코드가 한 곳도 없어서 모든 기억이 NULL 이었고,
 * NULL 은 3 으로 보정되므로 곱셈 항이 상수 0.6 이 된다 — 즉 세 축 중 하나가 죽은
 * 채로 돌았다. 그 결과 방금 들어온 STT 오인식 잔해가 최근성만으로 어르신의 인생
 * 이야기를 밀어냈다(실측: 반감기 30일이라 12일 된 시드 기억은 0.76, 오늘 만들어진
 * 잔해는 1.0).</p>
 *
 * <p>중요도는 "얼마나 흥미로운가"가 아니라 <b>"얼마나 오래 참인가"</b>다. 곱셈
 * 구조라 무관한 기억은 중요도가 높아도 올라오지 못하므로(relevance 하한 0.2),
 * 이 값의 실질적 역할은 "관련성이 비슷할 때 무엇을 먼저 꺼낼까"를 가르는 것이다.</p>
 *
 * <p>왜 하한을 2 로 두는가 — 1 을 주면 가중치가 0.2 라, 그 기억은 정확히 그
 * 주제를 물어봐도 거의 올라오지 않는다. 지우지 않기로 한 이상 되살아날 길은
 * 남겨 둔다. 정말 지워야 할 것은 중요도가 아니라 삭제로 다룬다.</p>
 */
final class MemoryImportancePolicy {

    /**
     * 대화에서 추출된 기억의 상한.
     *
     * <p>추출 기억은 STT 결과에 종속된다. 실측에서 "손자가 주말마다 놀러 온다"와
     * "심자가 주말마다 놀러 온다"가 나란히 저장됐는데, 둘을 기계가 구분할 방법이
     * 없다. 그래서 개별 내용을 판정하는 대신 출처 전체를 덜 신뢰한다 — 사람이
     * 큐레이션한 시드보다 낮게 둔다.</p>
     */
    static final short CONVERSATION_DERIVED_CAP = 3;

    private static final short DEFAULT_IMPORTANCE = 3;

    /**
     * 분류별 기본 중요도.
     *
     * <p>분류가 이미 "얼마나 오래 참인가"를 담고 있어서 LLM 을 새로 부르지 않아도
     * 된다. 정체성·관계는 평생 가고, 일과는 자주 바뀌며, OTHER 는 대개 그 턴에만
     * 의미가 있는 일회성이다.</p>
     */
    private static final Map<MemoryType, Short> BY_TYPE = Map.of(
            MemoryType.LIFE_EVENT, (short) 5,
            MemoryType.PERSONAL_RELATIONSHIP, (short) 5,
            MemoryType.FAMILY_MEMORY, (short) 4,
            MemoryType.PREFERENCE, (short) 4,
            MemoryType.HOBBY, (short) 4,
            MemoryType.EMOTIONAL_EVENT, (short) 4,
            MemoryType.DAILY_ROUTINE, (short) 3,
            MemoryType.OTHER, (short) 2);

    private MemoryImportancePolicy() {
    }

    /**
     * 이 기억에 매길 중요도.
     *
     * @param type 기억 분류
     * @param conversationDerived 대화 발화에서 추출됐는가(온보딩·가디언웹 입력이면 false)
     */
    static short importanceFor(MemoryType type, boolean conversationDerived) {
        short base = BY_TYPE.getOrDefault(type, DEFAULT_IMPORTANCE);
        return conversationDerived ? (short) Math.min(base, CONVERSATION_DERIVED_CAP) : base;
    }
}
