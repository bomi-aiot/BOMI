package com.ssafy.bomi.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.application.ConversationSummaryService.SweepReport;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.llm.application.TextGenerator;
import com.ssafy.bomi.llm.config.LlmProperties;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * {@code ConversationSummaryService} 의 완료 조건을 검증한다 (S15P11E102-254).
 *
 * <p>{@code EmbeddingSyncServiceTest} 와 같은 모양이다 — 실제 JPA 저장소(H2, datajpa
 * 프로파일)와 결정적 가짜 {@code TextGenerator} 를 쓴다. 여기서 확인하는 것은 전부
 * "부기"(누가 뽑히는가, 몇 번 불렸는가, 실패가 어떻게 남는가)이지 Gemini 가 실제로
 * 무엇을 반환하는지가 아니다 — 그건 {@code GeminiTextGeneratorTest} 의 몫이다.</p>
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class ConversationSummaryServiceTest {

    @Autowired ConversationRepository conversationRepository;
    @Autowired ConversationMessageRepository messageRepository;
    @Autowired ConversationSummaryRepository summaryRepository;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired TestEntityManager em;

    private final UUID seniorId = UUID.randomUUID();

    private FakeTextGenerator textGenerator;
    private LlmProperties properties;
    private ConversationSummaryService service;

    @BeforeEach
    void setUp() {
        textGenerator = new FakeTextGenerator();
        properties = new LlmProperties();
        properties.setMaxCallsPerRun(20);
        properties.setMaxSummaryMessages(60);
        service = new ConversationSummaryService(conversationRepository, messageRepository,
            summaryRepository, textGenerator, properties, transactionManager);
    }

    // ── 기본값이 꺼짐 ────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ LLM 이 꺼져 있으면 저장소를 건드리지 않고 스킵한다")
    void skipsEntirelyWhenGenerationIsUnavailable() {
        textGenerator.available = false;
        closedConversationWithMessages(2, ConversationStatus.COMPLETED);

        SweepReport report = service.summarizeDue();

        assertThat(report.skipped()).isTrue();
        assertThat(report.summarized()).isZero();
        assertThat(textGenerator.calls).isZero();
        assertThat(summaryRepository.count()).isZero();
    }

    // ── 무엇을 요약하는가 ────────────────────────────────────────────────────

    @Test
    void summarizesAClosedConversationWithMessages() {
        Conversation conversation = closedConversationWithMessages(3, ConversationStatus.COMPLETED);

        SweepReport report = service.summarizeDue();
        em.flush();
        em.clear();

        assertThat(report.summarized()).isEqualTo(1);
        assertThat(report.failed()).isZero();
        ConversationSummary saved = summaryRepository
            .findByConversationIdAndSupersededByIdIsNull(conversation.getId())
            .orElseThrow();
        assertThat(saved.getSourceMessageCount()).isEqualTo(3);
        assertThat(saved.getContent()).isNotBlank();
    }

    @Test
    @DisplayName("★ 봉인된 대화는 절대 요약되지 않는다 (CLAUDE.md §9 T4)")
    void sealedConversationsAreNeverSummarized() {
        Conversation conversation = closedConversationWithMessages(2, ConversationStatus.COMPLETED);
        conversation.markSealed();
        conversationRepository.save(conversation);
        em.flush();

        SweepReport report = service.summarizeDue();

        assertThat(report.summarized()).isZero();
        assertThat(textGenerator.calls)
            .as("봉인된 대화의 원문은 애초에 프롬프트로 조립되어서도 안 된다")
            .isZero();
        assertThat(summaryRepository.count()).isZero();
    }

    @Test
    void aConversationWithNoMessagesIsNeverSummarizedEvenIfMarkedCompleted() {
        // findNeedingSummary 가 걸러야 하는 경계 사례 — 실제로는 CANCELLED 로만
        // 닫히지만, 방어적으로 메시지가 없는 COMPLETED 도 스킵되는지 확인한다.
        Conversation conversation = conversationRepository.save(Conversation.open(seniorId));
        conversation.end(ConversationStatus.COMPLETED);
        conversationRepository.save(conversation);
        em.flush();

        SweepReport report = service.summarizeDue();

        assertThat(report.summarized()).isZero();
        assertThat(textGenerator.calls).isZero();
    }

    // ── 지출 상한 ────────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 한 번 실행이 실행당 처리 상한을 넘지 않는다 — 이것은 지출 상한이다")
    void oneRunNeverExceedsMaxCallsPerRun() {
        properties.setMaxCallsPerRun(2);
        for (int i = 0; i < 5; i++) {
            closedConversationWithMessages(1, ConversationStatus.COMPLETED);
        }

        SweepReport report = service.summarizeDue();

        assertThat(report.summarized()).isEqualTo(2);
        assertThat(textGenerator.calls).isEqualTo(2);
        assertThat(summaryRepository.count()).isEqualTo(2);
    }

    // ── LLM 실패 ─────────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 한 대화의 LLM 실패가 나머지 배치를 막지 않고, 그 대화의 닫힘 상태도 건드리지 않는다")
    void aFailingGenerationCallLeavesTheConversationClosedAndDoesNotStopTheBatch() {
        // 두 대화의 대화 내용을 다르게 줘서, 가짜 생성기가 "어느 프롬프트인지"로
        // 실패를 골라 낼 수 있게 한다 — 대화 id 는 프롬프트 문자열에 실리지 않는다
        // (buildPrompt 는 발화 내용만 담는다).
        Conversation willFail = closedConversationWithMessages(1, ConversationStatus.COMPLETED, "실패할대화");
        Conversation willSucceed = closedConversationWithMessages(1, ConversationStatus.COMPLETED, "성공할대화");
        textGenerator.explodeWhenPromptContains = "실패할대화";

        SweepReport report = service.summarizeDue();
        em.flush();
        em.clear();

        assertThat(report.failed()).isEqualTo(1);
        assertThat(report.summarized()).isEqualTo(1);
        assertThat(summaryRepository.findByConversationIdAndSupersededByIdIsNull(willFail.getId()))
            .as("실패한 대화는 요약 없이 남는다 — 다음 스윕이 재시도한다")
            .isEmpty();
        assertThat(summaryRepository.findByConversationIdAndSupersededByIdIsNull(willSucceed.getId()))
            .isPresent();
        // 완료 조건: LLM 실패가 대화 자체의 종료 상태·발화를 건드리면 안 된다.
        Conversation reloaded = conversationRepository.findById(willFail.getId()).orElseThrow();
        assertThat(reloaded.getStatus()).isEqualTo(ConversationStatus.COMPLETED);
        assertThat(reloaded.getEndedAt()).isNotNull();
    }

    // ── 중복 방지 ────────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 같은 스윕을 두 번 돌려도 요약이 중복 생성되지 않는다")
    void runningTheSweepTwiceDoesNotDuplicateASummary() {
        closedConversationWithMessages(2, ConversationStatus.COMPLETED);

        SweepReport first = service.summarizeDue();
        SweepReport second = service.summarizeDue();

        assertThat(first.summarized()).isEqualTo(1);
        assertThat(second.summarized())
            .as("findNeedingSummary 가 이미 요약이 있는 대화를 후보에서 뺀다")
            .isZero();
        assertThat(second.failed()).isZero();
        assertThat(summaryRepository.count()).isEqualTo(1);
        assertThat(textGenerator.calls).isEqualTo(1);
    }

    // ── 도우미 ───────────────────────────────────────────────────────────────

    /**
     * 대화마다 분명히 다른 (started_at, ended_at) 을 만든다.
     *
     * <p>{@code Conversation.open()}/{@code end()} 는 아직 시계 주입이 안 된 실제
     * 벽시계({@code OffsetDateTime.now()})를 쓴다(기존 코드, 이 티켓 범위 밖). 이
     * 테스트처럼 여러 대화를 한 루프에서 연달아 만들면 두 번의 {@code now()} 호출이
     * 같은 시각에 떨어져 {@code conversation_summary} 의
     * {@code UNIQUE(senior_id, summary_type, period_started_at, period_ended_at)} 제약에
     * 부딪힐 수 있다 — {@code EmbeddingSyncServiceTest.persistSummary} 가 이미 겪고
     * 문서화해 둔 것과 같은 종류의 충돌이다. 실제로 이 헬퍼도 한 번 그 충돌로
     * 죽었다(다섯 대화를 연달아 만드는 지출-상한 테스트에서). 카운터로 분(minute)
     * 단위 간격을 강제해 우회한다 — {@code conversation.end()} 가 세운 실제 시각을
     * 반사(reflection)로 결정적인 값으로 덮어쓴다.</p>
     */
    private int conversationCounter = 0;

    private Conversation closedConversationWithMessages(int messageCount, ConversationStatus status) {
        return closedConversationWithMessages(messageCount, status, "말");
    }

    private Conversation closedConversationWithMessages(
        int messageCount, ConversationStatus status, String contentPrefix) {
        int index = ++conversationCounter;
        OffsetDateTime startedAt = OffsetDateTime.parse("2026-01-01T00:00:00Z").plusHours(index);
        OffsetDateTime endedAt = startedAt.plusMinutes(messageCount);

        Conversation conversation = conversationRepository.save(Conversation.open(seniorId));
        org.springframework.test.util.ReflectionTestUtils.setField(
            conversation, "startedAt", startedAt);
        for (int i = 0; i < messageCount; i++) {
            messageRepository.save(ConversationMessage.reactive(
                conversation.getId(), i, MessageRole.SENIOR, contentPrefix + " " + i,
                startedAt.plusMinutes(i)));
        }
        conversation.end(status);
        org.springframework.test.util.ReflectionTestUtils.setField(
            conversation, "endedAt", endedAt);
        Conversation saved = conversationRepository.save(conversation);
        em.flush();
        return saved;
    }

    /** 네트워크를 절대 타지 않는, 결정적인 가짜 생성기. */
    private static class FakeTextGenerator implements TextGenerator {
        boolean available = true;
        int calls = 0;
        String explodeWhenPromptContains = null;

        @Override
        public String generate(String prompt) {
            calls++;
            if (explodeWhenPromptContains != null && prompt.contains(explodeWhenPromptContains)) {
                throw new GenerationFailedException("model refused this conversation");
            }
            return "요약: " + prompt.length() + "자 분량의 대화입니다.";
        }

        @Override
        public boolean isAvailable() {
            return available;
        }
    }
}
