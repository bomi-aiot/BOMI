package com.ssafy.bomi.conversation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.conversation.config.ConversationLifecycleProperties;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

/**
 * {@code ConversationLifecycleService} 의 완료 조건을 직접 검증한다 (S15P11E102-254).
 *
 * <p>왜 실제 JPA 인가 — {@code openOrContinue}·{@code closeIdleConversations} 은 둘 다
 * {@code findMaxOccurredAt}·{@code existsByConversationId} 같은 커스텀 쿼리에 의존한다.
 * 저장소를 mock 으로 대체하면 그 쿼리 자체가 맞는지는 검증하지 못하고 "서비스가 저장소를
 * 올바르게 부르는가"만 남는데, 이 완료 조건("30분 지나면 닫힌다", "발화 유무로
 * COMPLETED/CANCELLED 를 가른다")은 정확히 쿼리 결과에 좌우된다.</p>
 *
 * <p>시간은 {@link MutableClock} 으로 직접 돌린다 — CLAUDE.md §15 의 정신(실제로 30분을
 * 기다리지 않는다)을 백엔드 테스트에서도 지킨다. {@code openOrContinue} 자체는 시계를 안
 * 쓴다({@code occurredAt} 을 그대로 "지금"으로 받는다) — {@code closeIdleConversations} 만
 * 주입된 {@link Clock} 을 읽는다.</p>
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class ConversationLifecycleServiceTest {

    @Autowired ConversationRepository conversationRepository;
    @Autowired ConversationMessageRepository messageRepository;
    @Autowired TestEntityManager em;

    private MutableClock clock;
    private ConversationLifecycleProperties properties;
    private ConversationLifecycleService service;

    private final UUID seniorId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        // 실제 지금 근처에서 시작한다. Conversation.open() 은 startedAt 을 (아직 시계
        // 주입이 안 된 기존 코드라) 진짜 벽시계로 찍는다 — 이 테스트의 시계를 그와
        // 동떨어진 임의의 날짜에 고정하면, 메시지가 하나도 없어 startedAt 에 기대는
        // 케이스(발화 없이 방치된 대화)의 "경과 시간"이 실제 30분과 무관한 값이 되어
        // 우연히만 맞거나 우연히만 틀리는 테스트가 된다.
        clock = new MutableClock(Instant.now(), ZoneOffset.UTC);
        properties = new ConversationLifecycleProperties();
        properties.setIdleTimeout(Duration.ofMinutes(30));
        properties.setRawRetentionDays(30);
        service = new ConversationLifecycleService(
            conversationRepository, messageRepository, properties, clock);
    }

    // ── openOrContinue ───────────────────────────────────────────────────────

    @Test
    void nullConversationIdOpensANewOne() {
        UUID id = service.openOrContinue(seniorId, null, OffsetDateTime.now(clock));

        Conversation saved = conversationRepository.findById(id).orElseThrow();
        assertThat(saved.getSeniorId()).isEqualTo(seniorId);
        assertThat(saved.getStatus()).isEqualTo(ConversationStatus.OPEN);
    }

    @Test
    void unknownConversationIdThrows() {
        assertThatThrownBy(() ->
            service.openOrContinue(seniorId, UUID.randomUUID(), OffsetDateTime.now(clock)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("unknown conversationId");
    }

    @Test
    void aConversationBelongingToAnotherSeniorThrows() {
        Conversation someoneElses =
            conversationRepository.save(Conversation.open(UUID.randomUUID()));
        em.flush();

        assertThatThrownBy(() -> service.openOrContinue(
            seniorId, someoneElses.getId(), OffsetDateTime.now(clock)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("does not belong to senior");
    }

    @Test
    void continuesTheSameConversationWithinTheIdleWindow() {
        OffsetDateTime firstTurn = OffsetDateTime.now(clock);
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        messageRepository.save(ConversationMessage.reactive(
            open.getId(), 0, MessageRole.SENIOR, "안녕하세요", firstTurn));
        em.flush();

        // 유휴시간(30분) 안쪽인 20분 뒤.
        UUID id = service.openOrContinue(
            seniorId, open.getId(), firstTurn.plusMinutes(20));

        assertThat(id).isEqualTo(open.getId());
        assertThat(conversationRepository.findById(open.getId()).orElseThrow().getStatus())
            .isEqualTo(ConversationStatus.OPEN);
    }

    @Test
    void idleTimeoutExceededClosesTheOldConversationAndOpensANewOne() {
        OffsetDateTime firstTurn = OffsetDateTime.now(clock);
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        messageRepository.save(ConversationMessage.reactive(
            open.getId(), 0, MessageRole.SENIOR, "안녕하세요", firstTurn));
        em.flush();

        // 유휴시간(30분)을 넘긴 31분 뒤.
        UUID newId = service.openOrContinue(
            seniorId, open.getId(), firstTurn.plusMinutes(31));

        assertThat(newId).isNotEqualTo(open.getId());
        Conversation closed = conversationRepository.findById(open.getId()).orElseThrow();
        // 발화가 있었으므로 COMPLETED — CANCELLED 는 완료 조건이 명시한 "발화 없음" 전용이다.
        assertThat(closed.getStatus()).isEqualTo(ConversationStatus.COMPLETED);
        assertThat(closed.getEndedAt()).isNotNull();
        assertThat(conversationRepository.findById(newId).orElseThrow().getStatus())
            .isEqualTo(ConversationStatus.OPEN);
    }

    @Test
    void aConversationAlreadyClosedByAnotherPathSilentlyGetsAFreshOne() {
        Conversation closed = conversationRepository.save(Conversation.open(seniorId));
        closed.end(ConversationStatus.COMPLETED);
        conversationRepository.save(closed);
        em.flush();

        // 예외가 아니라 새 대화 — 완료 조건이 명시한 복구 동작이다(스윕이 먼저 닫았을 수 있다).
        UUID newId = service.openOrContinue(seniorId, closed.getId(), OffsetDateTime.now(clock));

        assertThat(newId).isNotEqualTo(closed.getId());
        assertThat(conversationRepository.findById(newId).orElseThrow().getStatus())
            .isEqualTo(ConversationStatus.OPEN);
    }

    // ── end() ─────────────────────────────────────────────────────────────────

    @Test
    void endRejectsOpenAsATerminalStatus() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        assertThatThrownBy(() ->
            service.end(open.getId(), seniorId, ConversationStatus.OPEN, false))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void endRejectsANullStatus() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        assertThatThrownBy(() -> service.end(open.getId(), seniorId, null, false))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void endOnAnUnknownConversationThrows() {
        assertThatThrownBy(() ->
            service.end(UUID.randomUUID(), seniorId, ConversationStatus.COMPLETED, false))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("unknown conversationId");
    }

    @Test
    void endForTheWrongSeniorThrows() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        assertThatThrownBy(() -> service.end(
            open.getId(), UUID.randomUUID(), ConversationStatus.COMPLETED, false))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("does not belong to senior");
    }

    @Test
    void endAppliesTheTerminalStatusAndSchedulesRawExpiry() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        Conversation ended = service.end(open.getId(), seniorId, ConversationStatus.FAILED, false);

        assertThat(ended.getStatus()).isEqualTo(ConversationStatus.FAILED);
        assertThat(ended.getEndedAt()).isNotNull();
        assertThat(ended.getRawMessagesExpiresAt())
            .isEqualTo(ended.getEndedAt().plusDays(properties.getRawRetentionDays()));
    }

    @Test
    void endMarksTheConversationSealedWhenAsked() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        Conversation ended = service.end(open.getId(), seniorId, ConversationStatus.COMPLETED, true);

        assertThat(ended.isSealed()).isTrue();
    }

    @Test
    void nullOrFalseSealedLeavesTheConversationUnsealed() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        Conversation ended = service.end(open.getId(), seniorId, ConversationStatus.COMPLETED, null);

        assertThat(ended.isSealed()).isFalse();
    }

    /**
     * 로봇의 아웃박스가 같은 종료를 재시도로 두 번 보낼 수 있다. 두 번째 호출이 첫 번째
     * 판정을 덮어쓰면 "왜 새벽 3시에 실패했나"를 되짚을 근거가 사라진다.
     */
    @Test
    void endCalledTwiceKeepsTheFirstTerminalStatus() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        service.end(open.getId(), seniorId, ConversationStatus.FAILED, false);
        Conversation second = service.end(open.getId(), seniorId, ConversationStatus.COMPLETED, false);

        assertThat(second.getStatus())
            .as("두 번째 호출의 값(COMPLETED)이 첫 번째 판정(FAILED)을 덮어쓰면 안 된다")
            .isEqualTo(ConversationStatus.FAILED);
    }

    // ── closeIdleConversations (스윕) ────────────────────────────────────────

    @Test
    void sweepClosesAnIdleConversationWithMessagesAsCompleted() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        messageRepository.save(ConversationMessage.reactive(
            open.getId(), 0, MessageRole.SENIOR, "안녕하세요", OffsetDateTime.now(clock)));
        em.flush();

        clock.advanceBy(Duration.ofMinutes(31));
        int closed = service.closeIdleConversations();

        assertThat(closed).isEqualTo(1);
        assertThat(conversationRepository.findById(open.getId()).orElseThrow().getStatus())
            .isEqualTo(ConversationStatus.COMPLETED);
    }

    @Test
    void sweepClosesAnIdleConversationWithNoMessagesAsCancelled() {
        // 발화 하나 없이 열리기만 하고 방치된 대화 — 완료 조건이 명시한 CANCELLED 경로다.
        conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        clock.advanceBy(Duration.ofMinutes(31));
        int closed = service.closeIdleConversations();

        assertThat(closed).isEqualTo(1);
        assertThat(conversationRepository.findByStatus(ConversationStatus.CANCELLED))
            .hasSize(1);
    }

    @Test
    void sweepLeavesAFreshConversationOpen() {
        conversationRepository.save(Conversation.open(seniorId));
        em.flush();

        // 유휴시간 안쪽 — 아직 닫을 때가 아니다.
        clock.advanceBy(Duration.ofMinutes(5));
        int closed = service.closeIdleConversations();

        assertThat(closed).isZero();
        assertThat(conversationRepository.findByStatus(ConversationStatus.OPEN)).hasSize(1);
    }

    @Test
    void runningTheSweepTwiceOnlyClosesTheConversationOnce() {
        Conversation open = conversationRepository.save(Conversation.open(seniorId));
        messageRepository.save(ConversationMessage.reactive(
            open.getId(), 0, MessageRole.SENIOR, "안녕하세요", OffsetDateTime.now(clock)));
        em.flush();
        clock.advanceBy(Duration.ofMinutes(31));

        int firstRun = service.closeIdleConversations();
        int secondRun = service.closeIdleConversations();

        assertThat(firstRun).isEqualTo(1);
        assertThat(secondRun)
            .as("이미 닫힌 대화는 두 번째 스윕의 findByStatus(OPEN) 대상이 아니다")
            .isZero();
    }

    /**
     * 실제로 흐르는 {@link Clock}. {@code closeIdleConversations} 가 매번 새 인스턴스를
     * 만들지 않고 이 하나를 계속 읽으므로, 테스트가 실제 30분을 기다리지 않고 시각을
     * 직접 앞으로 돌릴 수 있다(CLAUDE.md §15 의 압축 시계 정신).
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
