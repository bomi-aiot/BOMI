package com.ssafy.bomi.fact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.fact.application.FactCandidateCancellationService;
import com.ssafy.bomi.fact.application.RobotClarificationService;
import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;

/**
 * "기억하지 마"의 서버 절반 (S15P11E102-348) — 실제 PostgreSQL 검증.
 *
 * <p>지키는 약속은 하나다: <b>어르신이 지우라고 한 대화의 미확정 후보는 어떤
 * 경로로도 다시 살아나지 않는다.</b> 이 약속이 조용히 깨지면 — 지운 이야기가
 * 며칠 뒤 재질의로 되살아나면 — 어르신은 로봇의 "지웠어요"를 다시 믿지 않게
 * 되고, T4 신뢰 위에 서 있는 T3 동의 구조(CLAUDE.md §9)가 함께 무너진다.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
@Transactional
class FactCandidateCancellationServiceTest {

    private static EmbeddedPostgres postgres;

    @Autowired private FactCandidateCancellationService cancellationService;
    @Autowired private RobotClarificationService clarificationService;
    @Autowired private FactCandidateRepository candidateRepository;
    @Autowired private ConversationRepository conversationRepository;
    @Autowired private AppUserRepository appUserRepository;

    private AppUser senior;
    private Conversation conversation;

    @BeforeAll
    static void startPostgres() throws IOException {
        postgres = EmbeddedPostgres.start();
    }

    @AfterAll
    static void stopPostgres() throws IOException {
        if (postgres != null) {
            postgres.close();
        }
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> postgres.getJdbcUrl("postgres", "postgres"));
        registry.add("spring.datasource.username", () -> "postgres");
        registry.add("spring.datasource.password", () -> "");
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    }

    @BeforeEach
    void setUpSeniorAndConversation() {
        senior = appUserRepository.save(AppUser.create("SENIOR", "김순자", null, "순자님"));
        conversation = conversationRepository.save(Conversation.open(senior.getId()));
    }

    // ── 완료 조건: 대화 단위 취소 ────────────────────────────────────────────

    @Test
    void cancelsEveryUnconfirmedCandidateOfTheConversation() {
        FactCandidate captured = candidateIn(conversation, "family_event");
        FactCandidate awaiting = candidateIn(conversation, "daily_routine");
        awaiting.needsClarification(
            ClarificationReason.MISSING_REQUIRED_FIELD, List.of("content"));
        candidateRepository.saveAndFlush(awaiting);

        int cancelled = cancellationService.cancelBySenior(senior.getId(), conversation.getId());

        assertThat(cancelled).isEqualTo(2);
        assertThat(reload(captured).getStatus()).isEqualTo(FactCandidateStatus.CANCELLED_BY_SENIOR);
        assertThat(reload(awaiting).getStatus()).isEqualTo(FactCandidateStatus.CANCELLED_BY_SENIOR);
    }

    @Test
    void otherConversationsAreLeftAlone() {
        // "아까 그 이야기"를 지우라는 요청이 어제의 다른 대화까지 지우면, 그것은
        // 어르신이 부탁한 것보다 더 많은 기억을 지우는 것이다 — 과잉 삭제 방지.
        Conversation earlier = conversationRepository.save(Conversation.open(senior.getId()));
        FactCandidate untouched = candidateIn(earlier, "hobby");

        int cancelled = cancellationService.cancelBySenior(senior.getId(), conversation.getId());

        assertThat(cancelled).isZero();
        assertThat(reload(untouched).getStatus()).isEqualTo(FactCandidateStatus.CAPTURED);
    }

    // ── 완료 조건: 취소된 후보는 재질의에 나타나지 않는다 ────────────────────

    @Test
    void aCancelledCandidateNeverComesBackAsAClarification() {
        FactCandidate candidate = candidateIn(conversation, "medication_note");
        candidate.needsClarification(
            ClarificationReason.MISSING_REQUIRED_FIELD, List.of("content"));
        candidateRepository.saveAndFlush(candidate);
        assertThat(clarificationService.activeCandidate(senior.getId())).isPresent();

        cancellationService.cancelBySenior(senior.getId(), conversation.getId());

        assertThat(clarificationService.activeCandidate(senior.getId()))
            .as("지운 이야기가 재질의로 되살아나면 '지웠어요'는 거짓말이 된다")
            .isEmpty();
    }

    // ── 정직한 한계: 굳은 후보는 이 경로로 지우지 않는다 ─────────────────────

    @Test
    void confirmedCandidatesAreNotTouched() {
        FactCandidate confirmed = candidateIn(conversation, "family_event");
        confirmed.confirm(Map.of("content", "손자가 다녀갔다"), senior.getId());
        candidateRepository.saveAndFlush(confirmed);

        int cancelled = cancellationService.cancelBySenior(senior.getId(), conversation.getId());

        assertThat(cancelled).isZero();
        assertThat(reload(confirmed).getStatus()).isEqualTo(FactCandidateStatus.CONFIRMED);
    }

    @Test
    void cancellingAConfirmedCandidateDirectlyIsRejected() {
        FactCandidate confirmed = candidateIn(conversation, "family_event");
        confirmed.confirm(Map.of("content", "손자가 다녀갔다"), senior.getId());

        assertThatThrownBy(confirmed::cancelBySenior)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("unconfirmed");
    }

    // ── 멱등성: 재시도 큐가 중복 전송해도 안전하다 ──────────────────────────

    @Test
    void cancellingTwiceIsIdempotent() {
        FactCandidate candidate = candidateIn(conversation, "family_event");

        assertThat(cancellationService.cancelBySenior(senior.getId(), conversation.getId()))
            .isEqualTo(1);
        assertThat(cancellationService.cancelBySenior(senior.getId(), conversation.getId()))
            .isZero();
        assertThat(reload(candidate).getStatus())
            .isEqualTo(FactCandidateStatus.CANCELLED_BY_SENIOR);
    }

    // ── 소유권: 다른 어르신의 기억을 이 어르신의 요청으로 지울 수 없다 ───────

    @Test
    void aForeignConversationIsRejectedLoudly() {
        AppUser other = appUserRepository.save(AppUser.create("SENIOR", "박영감", null, "영감님"));
        Conversation foreign = conversationRepository.save(Conversation.open(other.getId()));

        assertThatThrownBy(() ->
                cancellationService.cancelBySenior(senior.getId(), foreign.getId()))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("does not belong to senior");
    }

    @Test
    void anUnknownConversationIsRejectedLoudly() {
        assertThatThrownBy(() ->
                cancellationService.cancelBySenior(senior.getId(), UUID.randomUUID()))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("unknown conversationId");
    }

    // ── 헬퍼 ─────────────────────────────────────────────────────────────────

    /** 이 대화에서 나온 CAPTURED 후보 하나. sourceMessageId 는 논리 참조라 임의 UUID 로 충분하다. */
    private FactCandidate candidateIn(Conversation inConversation, String factType) {
        FactCandidate candidate = FactCandidate.fromConversationMessage(
            senior.getId(), inConversation.getId(), UUID.randomUUID(),
            FactTargetDomain.MEMORY, factType, FactOperation.CREATE,
            Map.of("content", "테스트 후보"), RiskLevel.NORMAL);
        return candidateRepository.saveAndFlush(candidate);
    }

    private FactCandidate reload(FactCandidate candidate) {
        return candidateRepository.findById(candidate.getId()).orElseThrow();
    }
}
