package com.ssafy.bomi.fact.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.memory.domain.MemoryType;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

/**
 * 기억 중요도 정책 (2026-08-10).
 *
 * <p>이 값이 비어 있으면 {@code ConversationContextService.score} 의
 * {@code similarity × importance × recency} 에서 한 축이 상수가 된다. 실측에서
 * 그 결과 오늘 만들어진 STT 오인식 잔해가 12일 된 인생 이야기를 밀어냈다.</p>
 */
class MemoryImportancePolicyTest {

    @ParameterizedTest
    @EnumSource(MemoryType.class)
    @DisplayName("어떤 분류든 값을 낸다 — NULL 로 되돌아가는 길이 없어야 한다")
    void everyTypeGetsAnImportance(MemoryType type) {
        assertThat(MemoryImportancePolicy.importanceFor(type, false)).isBetween((short) 2, (short) 5);
        assertThat(MemoryImportancePolicy.importanceFor(type, true)).isBetween((short) 2, (short) 5);
    }

    @ParameterizedTest
    @EnumSource(MemoryType.class)
    @DisplayName("1 은 쓰지 않는다 — 가중치 0.2 면 그 주제를 물어도 올라오지 못한다")
    void noMemoryIsBuriedBeyondRecovery(MemoryType type) {
        assertThat(MemoryImportancePolicy.importanceFor(type, true)).isGreaterThanOrEqualTo((short) 2);
    }

    @Test
    @DisplayName("정체성·관계는 가장 오래 참이므로 가장 높다")
    void enduringFactsRankHighest() {
        assertThat(MemoryImportancePolicy.importanceFor(MemoryType.LIFE_EVENT, false)).isEqualTo((short) 5);
        assertThat(MemoryImportancePolicy.importanceFor(MemoryType.PERSONAL_RELATIONSHIP, false))
                .isEqualTo((short) 5);
    }

    @Test
    @DisplayName("OTHER 는 대개 그 턴에만 의미가 있는 일회성이라 가장 낮다")
    void oneOffChatterRanksLowest() {
        assertThat(MemoryImportancePolicy.importanceFor(MemoryType.OTHER, false)).isEqualTo((short) 2);
    }

    @Test
    @DisplayName("대화에서 추출된 기억은 STT 품질에 종속되므로 상한을 둔다")
    void conversationDerivedMemoriesAreCapped() {
        // "손자가 주말마다 놀러 온다"와 "심자가 주말마다 놀러 온다"를 기계가 구분할
        // 수 없다. 개별 내용을 판정하는 대신 출처 전체를 덜 신뢰한다.
        assertThat(MemoryImportancePolicy.importanceFor(MemoryType.PERSONAL_RELATIONSHIP, true))
                .isEqualTo(MemoryImportancePolicy.CONVERSATION_DERIVED_CAP);
        assertThat(MemoryImportancePolicy.importanceFor(MemoryType.LIFE_EVENT, true))
                .isEqualTo(MemoryImportancePolicy.CONVERSATION_DERIVED_CAP);
    }

    @Test
    @DisplayName("상한은 낮추기만 한다 — 이미 낮은 값을 끌어올리지 않는다")
    void theCapNeverRaisesAnImportance() {
        assertThat(MemoryImportancePolicy.importanceFor(MemoryType.OTHER, true)).isEqualTo((short) 2);
    }

    @Test
    @DisplayName("온보딩·가디언웹 입력은 사람이 확인한 값이라 상한을 받지 않는다")
    void curatedSourcesKeepTheirFullWeight() {
        assertThat(MemoryImportancePolicy.importanceFor(MemoryType.LIFE_EVENT, false))
                .isGreaterThan(MemoryImportancePolicy.CONVERSATION_DERIVED_CAP);
    }
}
