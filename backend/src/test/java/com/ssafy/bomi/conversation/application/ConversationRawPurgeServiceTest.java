package com.ssafy.bomi.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.conversation.application.ConversationRawPurgeService.PurgeReport;
import com.ssafy.bomi.conversation.config.ConversationLifecycleProperties;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.onboarding.domain.OnboardingAnswer;
import com.ssafy.bomi.onboarding.domain.OnboardingChannel;
import com.ssafy.bomi.onboarding.repository.OnboardingAnswerRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * {@code ConversationRawPurgeService} 의 선행조건 판정을 실제 DB 로 검증한다
 * (ERD §4, 검증 시나리오 31·32).
 *
 * <p><b>왜 mock 이 아니라 실제 JPA 인가.</b> 이 잡의 안전성은 전부
 * {@code ConversationRepository.findPurgeable} 한 개의 커스텀 JPQL 술어에 들어 있다.
 * 저장소를 mock 으로 대체하면 "서비스가 저장소를 올바르게 부르는가"만 남고 "그 술어가
 * 실제로 무엇을 고르는가"는 검증되지 않는데, 되돌릴 수 없는 삭제에서 위험한 것은
 * 정확히 후자다. {@code ConversationLifecycleServiceTest} 가 같은 이유를 이미 적어
 * 두었다.</p>
 *
 * <p>시간은 {@link MutableClock} 으로 직접 돌린다 — 보존기간 30일을 실제로 기다리지
 * 않는다.</p>
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class ConversationRawPurgeServiceTest {

    @Autowired ConversationRepository conversationRepository;
    @Autowired ConversationMessageRepository messageRepository;
    @Autowired ConversationSummaryRepository summaryRepository;
    @Autowired OnboardingAnswerRepository onboardingAnswerRepository;
    @Autowired FactCandidateRepository factCandidateRepository;
    @Autowired CareRecordRepository careRecordRepository;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired TestEntityManager em;

    private MutableClock clock;
    private ConversationLifecycleProperties properties;
    private ConversationRawPurgeService service;

    private final UUID seniorId = UUID.randomUUID();

    /** 요약 기간이 대화마다 겹치지 않게 하는 카운터 — {@link #addCurrentSummary} 참고. */
    private int summaryCount;

    @BeforeEach
    void setUp() {
        clock = new MutableClock(Instant.now(), ZoneOffset.UTC);
        properties = new ConversationLifecycleProperties();
        properties.setPurgeEnabled(true);          // 대부분의 테스트는 켠 상태를 본다
        properties.setPurgeBatchSize(200);
        service = newService();
    }

    private ConversationRawPurgeService newService() {
        return new ConversationRawPurgeService(
            conversationRepository, messageRepository, onboardingAnswerRepository,
            factCandidateRepository, careRecordRepository, properties, transactionManager, clock);
    }

    // ── 기본값이 꺼짐이다 (마지막 방어선) ─────────────────────────────────────

    /**
     * 이 한 줄이 "파괴적 배치가 기본 켜짐으로 배포되는" 사고를 막는 마지막 방어선이라
     * 별도 테스트로 못박는다. 누군가 기본값을 true 로 바꾸면 여기서 먼저 실패한다.
     */
    @Test
    @DisplayName("★ purge 의 기본값은 꺼짐이다")
    void purgeIsOffByDefault() {
        assertThat(new ConversationLifecycleProperties().isPurgeEnabled())
            .as("되돌릴 수 없는 삭제 잡의 기본값이 켜짐이면, 이 코드를 배포하는 것만으로 "
                + "어르신의 발화가 사라진다")
            .isFalse();
    }

    @Test
    @DisplayName("★ 꺼져 있으면 서비스를 직접 불러도 아무것도 지우지 않는다")
    void aDisabledPurgeDeletesNothingEvenWhenCalledDirectly() {
        UUID conversationId = purgeableConversation();
        properties.setPurgeEnabled(false);

        PurgeReport report = newService().purgeExpired();

        assertThat(report.skipped()).isTrue();
        assertThat(report.conversationsPurged()).isZero();
        assertThat(messageRepository.findIdsByConversationId(conversationId))
            .as("스위퍼 빈 조건부 생성은 1차 방어일 뿐이다. 서비스를 직접 부르는 경로도 막혀야 한다")
            .hasSize(1);
    }

    /**
     * {@code @ConditionalOnProperty} 에 {@code matchIfMissing = true} 가 실수로 붙는
     * 회귀를 잡는다 — 그 한 단어가 "꺼져 있으면 틱 자체가 없다"를 "설정 안 하면 켜진다"로
     * 뒤집는다.
     */
    @Test
    @DisplayName("★ purge-enabled 를 켜야만 스위퍼 빈이 생긴다")
    void theSweeperBeanOnlyExistsWhenExplicitlyEnabled() {
        ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of())
            .withBean(ConversationRawPurgeService.class,
                () -> mock(ConversationRawPurgeService.class))
            .withBean(ConversationLifecycleProperties.class, ConversationLifecycleProperties::new)
            .withUserConfiguration(ConversationRawPurgeSweeper.class);

        runner.run(context -> assertThat(context)
            .as("설정하지 않았는데 빈이 생기면 기본 꺼짐이 아니다")
            .doesNotHaveBean(ConversationRawPurgeSweeper.class));

        runner.withPropertyValues("bomi.conversation-lifecycle.purge-enabled=false")
            .run(context -> assertThat(context)
                .doesNotHaveBean(ConversationRawPurgeSweeper.class));

        runner.withPropertyValues("bomi.conversation-lifecycle.purge-enabled=true")
            .run(context -> assertThat(context)
                .as("명시적으로 켜면 빈이 있어야 한다 — 아니면 잡이 영영 안 돈다")
                .hasSingleBean(ConversationRawPurgeSweeper.class));
    }

    // ── 순서: 참조를 먼저 비우고 발화를 지운다 ────────────────────────────────

    /**
     * 이 테스트가 이 작업의 핵심이다. 발화가 사라지되 그 발화를 근거로 쓰던 세 테이블의
     * 행은 <b>살아남고</b>, 끊어진 UUID 대신 null 을 들고 있어야 한다.
     */
    @Test
    @DisplayName("★ 발화는 지워지고, 그 발화를 가리키던 세 테이블의 참조는 null 이 된다")
    void purgeDeletesUtterancesAndClearsTheThreeLogicalReferences() {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        UUID conversationId = conversation.getId();
        UUID citedMessageId = addMessage(conversationId, 0, "혈압약 먹었어");
        addMessage(conversationId, 1, "잘하셨어요");
        addMessage(conversationId, 2, "고마워");
        addCurrentSummary(conversationId);

        UUID answerId = saveOnboardingAnswer(conversationId, citedMessageId).getId();
        UUID candidateId = saveCandidate(conversationId, citedMessageId,
            FactCandidateStatus.MATERIALIZED).getId();
        UUID recordId = saveCareRecord(conversationId, citedMessageId).getId();
        em.flush();

        PurgeReport report = service.purgeExpired();

        assertThat(report.conversationsPurged()).isEqualTo(1);
        assertThat(report.messagesDeleted()).isEqualTo(3);
        assertThat(report.referencesCleared()).isEqualTo(3);

        assertThat(messageRepository.findIdsByConversationId(conversationId)).isEmpty();

        // 행 자체는 살아 있고, 발화 참조만 비었다.
        assertThat(onboardingAnswerRepository.findById(answerId).orElseThrow()
            .getSourceMessageId()).isNull();
        assertThat(factCandidateRepository.findById(candidateId).orElseThrow()
            .getSourceMessageId()).isNull();
        assertThat(careRecordRepository.findById(recordId).orElseThrow()
            .getSourceMessageId()).isNull();
    }

    /**
     * {@code clearSourceMessage()} 가 {@code linkEvidence}/{@code recordEvidence}/
     * {@code attachSources} 로 대체되지 않았음을 고정한다. 그 셋은 여러 필드를 한꺼번에
     * 덮어써서, 호출부가 한 번만 되먹이기를 빠뜨리면 대화 근거나 중복 방지 키까지 함께
     * 사라진다.
     */
    @Test
    @DisplayName("★ 발화 참조 말고 다른 컬럼은 하나도 건드리지 않는다")
    void purgeLeavesEveryOtherColumnOfTheCitingRowsIntact() {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        UUID conversationId = conversation.getId();
        UUID citedMessageId = addMessage(conversationId, 0, "혈압약 먹었어");
        addCurrentSummary(conversationId);

        OnboardingAnswer answer = saveOnboardingAnswer(conversationId, citedMessageId);
        FactCandidate candidate = saveCandidate(conversationId, citedMessageId,
            FactCandidateStatus.MATERIALIZED);
        CareRecord record = saveCareRecord(conversationId, citedMessageId);
        UUID sourceCandidateId = record.getSourceCandidateId();
        em.flush();

        service.purgeExpired();

        OnboardingAnswer foundAnswer =
            onboardingAnswerRepository.findById(answer.getId()).orElseThrow();
        assertThat(foundAnswer.getSourceConversationId())
            .as("발화는 지워져도 대화 행은 남는다. 대화 근거까지 비우면 요약과 이어 줄 끈이 없어진다")
            .isEqualTo(conversationId);
        assertThat(foundAnswer.getAnswerValue()).containsEntry("value", "혈압약");

        FactCandidate foundCandidate =
            factCandidateRepository.findById(candidate.getId()).orElseThrow();
        assertThat(foundCandidate.getConversationId()).isEqualTo(conversationId);
        assertThat(foundCandidate.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);

        CareRecord foundRecord = careRecordRepository.findById(record.getId()).orElseThrow();
        assertThat(foundRecord.getSourceConversationId()).isEqualTo(conversationId);
        assertThat(foundRecord.getSourceCandidateId())
            .as("uq_care_record_source_candidate 로 중복 실체화를 막는 키다. 여기가 비면 "
                + "같은 후보가 두 번 반영될 수 있는 상태로 되돌아간다")
            .isEqualTo(sourceCandidateId);
        assertThat(foundRecord.getScenarioId()).isNotNull();
        assertThat(foundRecord.getDetails()).containsEntry("drug", "혈압약");
    }

    @Test
    @DisplayName("다른 대화의 발화와 참조는 건드리지 않는다")
    void purgeDoesNotTouchAnotherConversation() {
        Conversation expired = closedConversation(expiredYesterday(), false);
        UUID expiredId = expired.getId();
        addMessage(expiredId, 0, "지워질 대화");
        addCurrentSummary(expiredId);

        // 아직 만료되지 않은 대화 — 발화도 참조도 그대로여야 한다.
        Conversation alive = closedConversation(OffsetDateTime.now(clock).plusDays(10), false);
        UUID aliveId = alive.getId();
        UUID aliveMessageId = addMessage(aliveId, 0, "남아야 할 대화");
        addCurrentSummary(aliveId);
        UUID aliveAnswerId = saveOnboardingAnswer(aliveId, aliveMessageId).getId();
        UUID aliveCandidateId =
            saveCandidate(aliveId, aliveMessageId, FactCandidateStatus.MATERIALIZED).getId();
        UUID aliveRecordId = saveCareRecord(aliveId, aliveMessageId).getId();
        em.flush();

        service.purgeExpired();

        assertThat(messageRepository.findIdsByConversationId(expiredId)).isEmpty();
        assertThat(messageRepository.findIdsByConversationId(aliveId))
            .containsExactly(aliveMessageId);
        assertThat(onboardingAnswerRepository.findById(aliveAnswerId).orElseThrow()
            .getSourceMessageId()).isEqualTo(aliveMessageId);
        assertThat(factCandidateRepository.findById(aliveCandidateId).orElseThrow()
            .getSourceMessageId()).isEqualTo(aliveMessageId);
        assertThat(careRecordRepository.findById(aliveRecordId).orElseThrow()
            .getSourceMessageId()).isEqualTo(aliveMessageId);
    }

    // ── 선행조건 ①: 보존기간 만료 ─────────────────────────────────────────────

    @Test
    @DisplayName("아직 만료되지 않았으면 지우지 않는다")
    void anUnexpiredConversationIsKept() {
        Conversation conversation =
            closedConversation(OffsetDateTime.now(clock).plusDays(1), false);
        addMessage(conversation.getId(), 0, "아직 살아 있어야 한다");
        addCurrentSummary(conversation.getId());
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isZero();
        assertThat(messageRepository.findIdsByConversationId(conversation.getId())).hasSize(1);
    }

    /** 모르는 것과 만료된 것은 다르다 — NULL 을 "지워도 된다"로 읽지 않는다. */
    @Test
    @DisplayName("★ 만료 시각이 NULL 이면 지우지 않는다 — '모른다'는 '만료됐다'가 아니다")
    void aNullExpiryIsNeverTreatedAsExpired() {
        Conversation conversation = closedConversation(null, false);
        addMessage(conversation.getId(), 0, "만료 시각을 모르는 대화");
        addCurrentSummary(conversation.getId());
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isZero();
        assertThat(messageRepository.findIdsByConversationId(conversation.getId())).hasSize(1);
    }

    @Test
    @DisplayName("경계는 만료 시각 '이하'다 — 정확히 그 순간이면 지운다")
    void theExpiryBoundaryIsInclusive() {
        OffsetDateTime expiresAt = OffsetDateTime.now(clock).plusMinutes(10);
        Conversation conversation = closedConversation(expiresAt, false);
        addMessage(conversation.getId(), 0, "경계 확인");
        addCurrentSummary(conversation.getId());
        em.flush();

        // 만료 1초 전 — 아직 아니다.
        clock.advanceBy(Duration.ofMinutes(10).minusSeconds(1));
        assertThat(service.purgeExpired().conversationsPurged()).isZero();

        // 만료 시각을 지난 순간 — 이제 지운다.
        clock.advanceBy(Duration.ofSeconds(2));
        assertThat(service.purgeExpired().conversationsPurged()).isEqualTo(1);
    }

    // ── 선행조건 ②: 필요한 요약 생성 ─────────────────────────────────────────

    @Test
    @DisplayName("★ 요약이 없으면 지우지 않는다 — 요약이 유일한 잔존 기록이어야 한다")
    void aConversationWithoutASummaryIsKept() {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        addMessage(conversation.getId(), 0, "요약이 아직 없다");
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isZero();
        assertThat(messageRepository.findIdsByConversationId(conversation.getId()))
            .as("요약 없이 지우면 그날 무슨 얘기를 했는지가 이 세상에서 사라진다")
            .hasSize(1);
    }

    @Test
    @DisplayName("대체된(superseded) 요약만 있으면 '현행 요약 없음'으로 본다")
    void aSupersededSummaryDoesNotCountAsTheCurrentSummary() {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        addMessage(conversation.getId(), 0, "요약이 대체됐다");
        ConversationSummary stale = addCurrentSummary(conversation.getId());
        stale.supersededBy(UUID.randomUUID());
        summaryRepository.save(stale);
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isZero();
        assertThat(messageRepository.findIdsByConversationId(conversation.getId())).hasSize(1);
    }

    /**
     * 봉인 대화는 {@code findNeedingSummary} 가 {@code sealed = false} 로 제외하므로
     * 요약이 <b>만들어지지 않는다</b>. 이 예외가 없으면 "요약 있어야 지운다"가
     * 봉인 대화에는 영원히 충족되지 않아, 어르신이 "우리끼리 얘기"라고 말한 가장 민감한
     * 발화만 평문으로 영구 보존된다 — 봉인이 지키려던 약속과 정확히 반대 결과다.
     */
    @Test
    @DisplayName("★ 봉인 대화는 요약이 없어도 지운다 — 없으면 가장 민감한 발화만 영구 보존된다")
    void aSealedConversationIsPurgedEvenWithoutASummary() {
        Conversation conversation = closedConversation(expiredYesterday(), true);
        addMessage(conversation.getId(), 0, "우리끼리 얘기인데");
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isEqualTo(1);
        assertThat(messageRepository.findIdsByConversationId(conversation.getId())).isEmpty();
    }

    @Test
    @DisplayName("봉인 대화라도 나머지 선행조건은 그대로 적용한다")
    void aSealedConversationStillObeysTheOtherPreconditions() {
        Conversation conversation = closedConversation(expiredYesterday(), true);
        UUID messageId = addMessage(conversation.getId(), 0, "우리끼리 얘기인데");
        saveCandidate(conversation.getId(), messageId, FactCandidateStatus.NEEDS_CONFIRMATION);
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged())
            .as("봉인은 요약 조건만 면제한다. 활성 후보가 있으면 봉인 여부와 무관하게 남긴다")
            .isZero();
        assertThat(messageRepository.findIdsByConversationId(conversation.getId())).hasSize(1);
    }

    // ── 선행조건 ③④: 활성 후보 해소 + 확정 사실의 최종 반영 ──────────────────

    /**
     * enum 전량을 훑는다. {@link FactCandidateStatus} 에 새 값이 추가되면 이 테스트가
     * 자동으로 그 값을 포함하므로, "지워도 되는 상태인가"를 반드시 판단하게 된다.
     * 판단을 빠뜨리면 그 상태의 후보를 가진 대화가 조용히 삭제 대상이 된다.
     */
    @ParameterizedTest
    @EnumSource(FactCandidateStatus.class)
    @DisplayName("★ 후보 상태별로 지워도 되는지가 갈린다 (enum 전량)")
    void onlySettledCandidatesAllowThePurge(FactCandidateStatus status) {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        UUID conversationId = conversation.getId();
        UUID messageId = addMessage(conversationId, 0, "혈압약 먹었어");
        addCurrentSummary(conversationId);
        saveCandidate(conversationId, messageId, status);
        em.flush();

        int purged = service.purgeExpired().conversationsPurged();

        boolean shouldBeKept = ConversationRawPurgeService.UNSETTLED.contains(status);
        if (shouldBeKept) {
            assertThat(purged)
                .as("%s 는 아직 정리되지 않은 후보다. 근거 발화를 지우면 되짚을 원본이 없다", status)
                .isZero();
            assertThat(messageRepository.findIdsByConversationId(conversationId)).hasSize(1);
        } else {
            assertThat(purged)
                .as("%s 는 끝난 후보다. 이 상태만 있으면 Raw 를 지울 수 있어야 한다", status)
                .isEqualTo(1);
            assertThat(messageRepository.findIdsByConversationId(conversationId)).isEmpty();
        }
    }

    /**
     * ★ 선행조건을 보는 축과 실제로 지우는 축이 갈라진 상태 (리뷰 지적, blocker).
     *
     * <p><b>왜 위 테스트가 이걸 못 잡는가.</b> {@code onlySettledCandidatesAllowThePurge}
     * 는 후보의 {@code conversationId} 와 {@code sourceMessageId} 가 <b>같은 대화</b>를
     * 가리키는 경우만 만든다. 두 값이 같으면 어느 축으로 확인하든 결과가 같아서, 축이
     * 틀렸다는 사실 자체가 드러나지 않는다.</p>
     *
     * <p><b>두 축은 실제로 갈라진다.</b> {@link FactCandidate#recordEvidence} 가 두 값을
     * 독립적으로 갱신하고(null 은 "건너뛴다"로 해석한다), 로봇의 재질의 경로
     * ({@code graph/handlers.py})는 {@code conversationId} 만 보내고
     * {@code sourceMessageId} 는 보내지 않는다. 그래서 아래 시나리오가 정상 운영 중에
     * 만들어진다.</p>
     *
     * <ol>
     *   <li>대화 A 에서 "혈압약 먹어야 하는데" → 후보(conversationId=A, sourceMessageId=msgA,
     *       NEEDS_CONFIRMATION)</li>
     *   <li>며칠 뒤 대화 B 에서 재질의 → {@code recordEvidence(B, null)} → conversationId 만
     *       B 로 옮겨가고 sourceMessageId 는 msgA 를 계속 가리킨다</li>
     *   <li>보호자가 확인하지 않아 후보는 여전히 NEEDS_CONFIRMATION
     *       ({@code FactCandidate.expire()} 는 호출자가 0건이라 자동 만료도 없다)</li>
     *   <li>대화 A 가 만료 → conversationId 축 확인은 "A 를 가리키는 미확정 후보가 없다"며
     *       통과 → {@code findBySourceMessageIdIn} 이 그 후보를 찾아 근거를 지우고 msgA 를
     *       <b>영구 삭제</b></li>
     * </ol>
     *
     * <p>백업도 소프트삭제도 감사 테이블도 없어 복구 경로가 없다.</p>
     */
    @Test
    @DisplayName("★ 후보가 다른 대화로 옮겨가도 근거 발화는 보호된다 (축이 갈라진 경우)")
    void aCandidateWhoseConversationMovedStillProtectsItsEvidence() {
        Conversation spoken = closedConversation(expiredYesterday(), false);
        UUID spokenId = spoken.getId();
        UUID evidenceId = addMessage(spokenId, 0, "혈압약 먹어야 하는데");
        addCurrentSummary(spokenId);

        // 재질의가 일어난, 아직 만료되지 않은 다른 대화.
        Conversation clarified = closedConversation(OffsetDateTime.now(clock).plusDays(30), false);

        FactCandidate candidate =
            saveCandidate(spokenId, evidenceId, FactCandidateStatus.NEEDS_CONFIRMATION);
        // 로봇 재질의 경로가 하는 일 그대로 — conversationId 만 보내고 sourceMessageId 는 null.
        candidate.recordEvidence(clarified.getId(), null);
        em.flush();

        int purged = service.purgeExpired().conversationsPurged();

        assertThat(purged)
            .as("후보의 conversationId 는 다른 대화를 가리키지만 근거 발화는 여기 있다")
            .isZero();
        assertThat(messageRepository.findIdsByConversationId(spokenId))
            .as("아직 확인 대기 중인 후보의 원본 발화가 사라지면 안 된다")
            .hasSize(1);
    }

    /**
     * {@code CONFIRMED} 는 "값은 굳었으나 아직 최종 테이블에 안 들어갔다"이다 — ERD §4 의
     * 네 번째 선행조건("확정 사실의 최종 반영")이 바로 이 상태를 가리킨다.
     */
    @Test
    @DisplayName("★ CONFIRMED(반영 전) 후보가 있으면 지우지 않는다")
    void aConfirmedButNotYetMaterializedCandidateBlocksThePurge() {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        UUID messageId = addMessage(conversation.getId(), 0, "혈압약 먹었어");
        addCurrentSummary(conversation.getId());
        saveCandidate(conversation.getId(), messageId, FactCandidateStatus.CONFIRMED);
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isZero();
        assertThat(messageRepository.findIdsByConversationId(conversation.getId())).hasSize(1);
    }

    // ── 방어 술어: OPEN 대화 ─────────────────────────────────────────────────

    @Test
    @DisplayName("OPEN 대화는 만료 시각이 있어도 지우지 않는다")
    void anOpenConversationIsNeverPurged() {
        // 정상 경로로는 만료 시각이 채워지지 않지만, 방어 술어가 실제로 도는지 본다.
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        open.scheduleRawExpiry(expiredYesterday());
        conversationRepository.save(open);
        addMessage(open.getId(), 0, "아직 대화 중이다");
        addCurrentSummary(open.getId());
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isZero();
        assertThat(messageRepository.findIdsByConversationId(open.getId())).hasSize(1);
    }

    // ── 상한과 멱등성 ────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 한 실행에서 batchSize 개를 넘겨 지우지 않는다 — 한 사고의 폭 상한")
    void oneRunNeverPurgesMoreThanTheBatchSize() {
        List<UUID> ids = List.of(
            purgeableConversation(), purgeableConversation(), purgeableConversation(),
            purgeableConversation(), purgeableConversation());
        properties.setPurgeBatchSize(2);
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isEqualTo(2);
        assertThat(remainingWithMessages(ids)).isEqualTo(3);

        assertThat(service.purgeExpired().conversationsPurged()).isEqualTo(2);
        assertThat(remainingWithMessages(ids)).isEqualTo(1);

        assertThat(service.purgeExpired().conversationsPurged()).isEqualTo(1);
        assertThat(remainingWithMessages(ids)).isZero();
    }

    /**
     * "발화가 남아 있는 대화만" 술어가 삭제 완료 표시를 겸한다 — 그래서 새 컬럼도,
     * 새 Flyway 마이그레이션도 필요 없다.
     */
    @Test
    @DisplayName("★ 두 번 돌려도 두 번째는 0건이고 예외가 없다 (멱등)")
    void runningThePurgeTwiceIsSafe() {
        UUID conversationId = purgeableConversation();
        em.flush();

        assertThat(service.purgeExpired().conversationsPurged()).isEqualTo(1);
        PurgeReport second = service.purgeExpired();

        assertThat(second.conversationsPurged()).isZero();
        assertThat(second.messagesDeleted()).isZero();
        assertThat(second.skipped()).isFalse();
        assertThat(messageRepository.findIdsByConversationId(conversationId)).isEmpty();
    }

    /** 이미 null 인 참조에 다시 null 을 넣는 것은 no-op 이어야 한다(크래시 후 재실행). */
    @Test
    @DisplayName("참조가 이미 비어 있어도 재실행이 안전하다")
    void clearingAnAlreadyClearedReferenceIsANoOp() {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        UUID messageId = addMessage(conversation.getId(), 0, "혈압약 먹었어");
        addCurrentSummary(conversation.getId());
        FactCandidate candidate =
            saveCandidate(conversation.getId(), messageId, FactCandidateStatus.MATERIALIZED);
        candidate.clearSourceMessage();
        factCandidateRepository.save(candidate);
        em.flush();

        PurgeReport report = service.purgeExpired();

        assertThat(report.conversationsPurged()).isEqualTo(1);
        assertThat(report.referencesCleared())
            .as("이미 비어 있던 참조는 조회에 걸리지 않으므로 세지 않는다")
            .isZero();
        assertThat(factCandidateRepository.findById(candidate.getId()).orElseThrow()
            .getSourceMessageId()).isNull();
    }

    // ── 테스트 데이터 ────────────────────────────────────────────────────────

    /** 만료 + 요약 있음 + 활성 후보 없음 + 발화 1건 — 지워져야 하는 최소 조합. */
    private UUID purgeableConversation() {
        Conversation conversation = closedConversation(expiredYesterday(), false);
        addMessage(conversation.getId(), 0, "지워도 되는 발화");
        addCurrentSummary(conversation.getId());
        return conversation.getId();
    }

    private long remainingWithMessages(List<UUID> conversationIds) {
        return conversationIds.stream()
            .filter(id -> !messageRepository.findIdsByConversationId(id).isEmpty())
            .count();
    }

    private OffsetDateTime expiredYesterday() {
        return OffsetDateTime.now(clock).minusDays(1);
    }

    private Conversation closedConversation(OffsetDateTime expiresAt, boolean sealed) {
        Conversation conversation = Conversation.open(seniorId);
        conversation.end(ConversationStatus.COMPLETED);
        conversation.scheduleRawExpiry(expiresAt);
        if (sealed) {
            conversation.markSealed();
        }
        return conversationRepository.save(conversation);
    }

    private UUID addMessage(UUID conversationId, int sequenceNo, String content) {
        return messageRepository.save(ConversationMessage.reactive(
            conversationId, sequenceNo, MessageRole.SENIOR, content,
            OffsetDateTime.now(clock))).getId();
    }

    /**
     * 대화 하나에 현행 요약 하나를 붙인다.
     *
     * <p>기간을 호출마다 어긋나게 잡는 이유: {@code uq_conversation_summary_period} 가
     * (senior_id, summary_type, period_started_at, period_ended_at) 유일이라, 한 어르신의
     * 여러 대화에 같은 기간의 요약을 달면 두 번째부터 제약에 걸린다. 실제로도 서로 다른
     * 대화의 요약 기간은 겹치지 않는다.</p>
     */
    private ConversationSummary addCurrentSummary(UUID conversationId) {
        OffsetDateTime periodEnd = OffsetDateTime.now(clock).minusMinutes(summaryCount++);
        return summaryRepository.save(ConversationSummary.forConversation(
            seniorId, conversationId, periodEnd.minusHours(1), periodEnd, "요약 본문", 1));
    }

    private OnboardingAnswer saveOnboardingAnswer(UUID conversationId, UUID messageId) {
        OnboardingAnswer answer = OnboardingAnswer.create(
            UUID.randomUUID(), "MEDICATION", OnboardingChannel.ROBOT, UUID.randomUUID(),
            Map.of("value", "혈압약"));
        answer.linkEvidence(conversationId, messageId);
        return onboardingAnswerRepository.save(answer);
    }

    private CareRecord saveCareRecord(UUID conversationId, UUID messageId) {
        CareRecord record = CareRecord.create(seniorId, "MEDICATION", Map.of("drug", "혈압약"));
        record.attachSources(UUID.randomUUID(), conversationId, messageId, UUID.randomUUID(),
            UUID.randomUUID());
        return careRecordRepository.save(record);
    }

    /** 원하는 상태의 후보를 만든다. 상태 전이는 엔티티가 허용하는 경로로만 밟는다. */
    private FactCandidate saveCandidate(UUID conversationId, UUID messageId,
        FactCandidateStatus status) {

        FactCandidate candidate = FactCandidate.fromConversationMessage(
            seniorId, conversationId, messageId, FactTargetDomain.CARE_RECORD,
            "medication_dose", FactOperation.CREATE, Map.of("drug", "혈압약"), RiskLevel.SENSITIVE);

        switch (status) {
            case CAPTURED -> { /* 생성 직후의 기본 상태다 */ }
            case NEEDS_CLARIFICATION -> candidate.needsClarification(
                ClarificationReason.MISSING_REQUIRED_FIELD, List.of("dose"));
            case NEEDS_CONFIRMATION -> candidate.needsConfirmation();
            case COORDINATION_REQUIRED -> candidate.requireCoordination(
                UUID.randomUUID(), OffsetDateTime.now(clock).plusDays(1));
            case CONFIRMED -> candidate.confirm(Map.of("dose", "1정"), UUID.randomUUID());
            case MATERIALIZED -> {
                candidate.confirm(Map.of("dose", "1정"), UUID.randomUUID());
                candidate.materialize(UUID.randomUUID());
            }
            case REJECTED -> candidate.reject();
            case EXPIRED -> candidate.expire(OffsetDateTime.now(clock));
            case CANCELLED_BY_SENIOR -> candidate.cancelBySenior();
        }

        return factCandidateRepository.save(candidate);
    }

    /**
     * 실제로 흐르는 {@link Clock}. 보존기간 경계를 실제로 기다리지 않고 확인한다
     * ({@code ConversationLifecycleServiceTest} 와 같은 도구).
     */
    private static final class MutableClock extends Clock {
        private Instant instant;
        private final ZoneId zone;

        MutableClock(Instant instant, ZoneId zone) {
            this.instant = instant;
            this.zone = zone;
        }

        void advanceBy(Duration duration) {
            instant = instant.plus(duration);
        }

        @Override
        public ZoneId getZone() {
            return zone;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return new MutableClock(instant, zone);
        }

        @Override
        public Instant instant() {
            return instant;
        }
    }
}
