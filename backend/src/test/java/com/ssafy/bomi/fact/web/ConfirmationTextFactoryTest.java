package com.ssafy.bomi.fact.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * {@link ConfirmationTextFactory} 단위 테스트.
 *
 * <p>왜 이 테스트가 있는가 — 로봇은 대화에서 건진 사실을 {@code {"content": "..."} }
 * 하나로만 보내는데(ai_chat {@code fact_contract.to_intake_payload}), 이 팩토리는
 * {@code note}/{@code title} 만 읽고 있었다. 그래서 실서버에서 보호자가 받은 문장이
 * <em>"정보 없음 관련 관찰이 감지되었습니다"</em> 였다 — 어르신이 무슨 말을 했는지
 * 한 글자도 없이, 문법만 멀쩡한 문장이다. 예외도 로그도 남지 않아 아무도 몰랐다.</p>
 *
 * <p>그래서 검증의 축은 "문구가 예쁜가"가 아니라 <b>어르신이 실제로 한 말이 문장 안에
 * 남아 있는가</b>, 그리고 <b>값이 없을 때 없는 값을 있는 척 끼워 넣지 않는가</b> 둘이다.</p>
 */
class ConfirmationTextFactoryTest {

    private final ConfirmationTextFactory factory = new ConfirmationTextFactory();

    private static FactCandidate careRecord(String factType, Map<String, Object> proposed) {
        return FactCandidate.fromConversationMessage(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                FactTargetDomain.CARE_RECORD, factType, FactOperation.CREATE,
                proposed, RiskLevel.SENSITIVE);
    }

    @Test
    void healthTextCarriesTheSpokenSentenceWhenOnlyContentIsGiven() {
        // 로봇이 실제로 보내는 모양. 이 한 건이 실서버에서 빈 카드로 나갔다.
        FactCandidate candidate = careRecord(
                "HEALTH_CONDITION", Map.of("content", "숨쉬기가 답답하고 숨이 안 쉬어진다."));

        ConfirmationTextFactory.ConfirmationText text = factory.create(candidate);

        assertThat(text.summary()).contains("숨쉬기가 답답하고 숨이 안 쉬어진다.");
        assertThat(text.question()).isNotBlank();
    }

    @Test
    void noneOfTheHealthTextEverSaysTheValueIsMissingWhenContentExists() {
        FactCandidate candidate = careRecord(
                "HEALTH_CONDITION", Map.of("content", "무릎이 시큰거린다."));

        ConfirmationTextFactory.ConfirmationText text = factory.create(candidate);

        // "정보 없음"이 문장 한가운데 박히는 것이 원래 증상이었다. 어떤 칸에도 없어야 한다.
        assertThat(text.title()).doesNotContain("정보 없음");
        assertThat(text.summary()).doesNotContain("정보 없음");
        assertThat(text.question()).doesNotContain("정보 없음");
        assertThat(text.evidence()).doesNotContain("정보 없음");
    }

    @Test
    void healthPrefersTheCuratedNoteOverRawContent() {
        // 온보딩 답변 경로는 note 를 채워 보낼 수 있다. 그쪽이 더 정제된 값이라 우선한다.
        FactCandidate candidate = careRecord("HEALTH_CONDITION",
                Map.of("content", "어제부터 무릎이 좀", "note", "무릎 통증이 어제부터 있음"));

        ConfirmationTextFactory.ConfirmationText text = factory.create(candidate);

        assertThat(text.summary()).contains("무릎 통증이 어제부터 있음");
    }

    @Test
    void healthFallsBackToASentenceThatDoesNotPretendWhenNothingIsReadable() {
        // 값이 정말 하나도 없을 때. 빈칸을 "정보 없음"으로 메우는 대신 문장 자체가 바뀐다.
        FactCandidate candidate = careRecord("HEALTH_CONDITION", Map.of("unexpectedKey", "x"));

        ConfirmationTextFactory.ConfirmationText text = factory.create(candidate);

        assertThat(text.summary()).isEqualTo("건강 관련 관찰이 감지되었습니다.");
        assertThat(text.summary()).doesNotContain("정보 없음");
    }

    @Test
    void blankContentIsTreatedAsMissingRatherThanQuotedAsAnEmptyString() {
        // 로봇의 to_intake_payload 는 content 를 str(...) 로 만들므로 "" 가 올 수 있다.
        // 그걸 그대로 쓰면 "''라고 말씀하셨습니다." 라는 문장이 나간다.
        FactCandidate candidate = careRecord("HEALTH_CONDITION", Map.of("content", "   "));

        ConfirmationTextFactory.ConfirmationText text = factory.create(candidate);

        assertThat(text.summary()).isEqualTo("건강 관련 관찰이 감지되었습니다.");
    }

    @Test
    void memoryTextStillUsesContentAsBefore() {
        FactCandidate candidate = FactCandidate.fromConversationMessage(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                FactTargetDomain.MEMORY, "HOBBY", FactOperation.CREATE,
                Map.of("content", "화분 가꾸는 것을 좋아한다."), RiskLevel.NORMAL);

        ConfirmationTextFactory.ConfirmationText text = factory.create(candidate);

        assertThat(text.summary()).isEqualTo("화분 가꾸는 것을 좋아한다.");
    }

    @Test
    void scheduleWithoutAStartTimeSaysSoInsteadOfPrintingAPlaceholder() {
        FactCandidate candidate = careRecord("APPOINTMENT", Map.of("title", "정형외과 진료"));

        ConfirmationTextFactory.ConfirmationText text = factory.create(candidate);

        assertThat(text.summary()).contains("정형외과 진료");
        assertThat(text.summary()).doesNotContain("정보 없음");
        assertThat(text.question()).doesNotContain("정보 없음");
    }
}
