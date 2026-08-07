package com.ssafy.bomi.conversation.application;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.conversation.config.ConversationLifecycleProperties;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.onboarding.domain.OnboardingAnswer;
import com.ssafy.bomi.onboarding.repository.OnboardingAnswerRepository;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 보존기간이 지난 원본 발화를 영구 삭제한다 — ERD §4 의 "Raw 삭제" 규칙을 실제로
 * 집행하는 유일한 자리 (검증 시나리오 31·32).
 *
 * <p><b>왜 존재하는가.</b> {@code conversation.raw_messages_expires_at} 은
 * {@code ConversationLifecycleService} 가 대화를 닫을 때마다 성실히 채워 왔지만, 저장소
 * 전체에서 <b>그 값을 읽는 코드가 하나도 없었다.</b> 즉 어르신의 모든 발화가 평문으로
 * 무기한 남아 있었고, "30일 뒤 지운다"는 설정은 지켜지는 것처럼 보이기만 했다. 이
 * 서비스가 그 컬럼의 최초 소비자다.</p>
 *
 * <p><b>★ 되돌릴 수 없다.</b> {@code conversation_message} 에는 백업도, 소프트 삭제도,
 * 감사 테이블도 없다. 선행조건 술어가 하나만 잘못돼도 어르신의 대화가 조용히 사라지고,
 * 그 사실을 알려 주는 것은 아무것도 없다. 그래서 방어를 세 겹으로 건다.</p>
 * <ol>
 *   <li><b>기본 꺼짐</b> — {@code purge-enabled} 가 명시적으로 켜져 있지 않으면
 *       {@code ConversationRawPurgeSweeper} 빈 자체가 만들어지지 않는다. 아래
 *       {@link #purgeExpired()} 는 그 위에 서비스 단독 호출 경로까지 한 번 더 막는다.</li>
 *   <li><b>배치 상한</b> — 한 실행에서 지우는 대화 수를 {@code purge-batch-size} 로
 *       제한한다. 잘못된 술어로 배포해도 첫 실행의 피해가 그 수를 넘지 않는다.</li>
 *   <li><b>부팅 경고 로그</b> — 켜져 있다는 사실을 기동 시 1회 {@code WARN} 으로 남긴다.</li>
 * </ol>
 *
 * <p><b>순서가 전부다.</b> 논리 참조를 <b>먼저</b> 비우고 발화를 <b>나중에</b> 지운다.
 * 반대로 하면 {@code onboarding_answer}·{@code fact_candidate}·{@code care_record} 에
 * 존재하지 않는 행을 가리키는 UUID 가 조용히 남는데, 물리 FK 도
 * {@code ON DELETE SET NULL} 도 없으므로(V1 주석) 그것을 되짚으려면 세 테이블을 전량
 * 훑어 "{@code conversation_message} 에 없는 id"를 역으로 구해야 한다 — 그때는 다른
 * 대화의 살아 있는 발화와 구분할 방법이 이미 사라진 뒤다.</p>
 *
 * <p><b>로그에 발화 원문을 절대 싣지 않는다.</b> 대화 id 와 건수만 남긴다. 지우는
 * 행위를 기록으로 남기려다 지워야 할 내용을 로그에 영구 보존하는 것은 그 자체로 모순이다
 * ({@code FactCandidateCancellationService} 가 세운 선례).</p>
 */
@Service
public class ConversationRawPurgeService {

    private static final Logger log = LoggerFactory.getLogger(ConversationRawPurgeService.class);

    /**
     * 이 상태의 후보가 하나라도 달린 대화의 Raw 는 지우지 않는다.
     *
     * <p>ERD §4 의 <b>두</b> 선행조건을 한 술어로 합친 것이다.</p>
     * <ul>
     *   <li><b>활성 후보 해소</b> — 앞의 넷은 아직 값이 굳지 않은 단계다
     *       ({@code FactCandidateCancellationService.CANCELLABLE} 와 같은 집합).
     *       재질의·확인·조율이 진행 중인데 근거 발화를 지우면 "왜 이렇게 기록됐나"에
     *       답할 수단이 사라진다.</li>
     *   <li><b>확정 사실의 최종 반영</b> — {@code CONFIRMED} 는 "값은 굳었으나 아직 최종
     *       테이블에 안 들어갔다"이다. {@code FactMaterializer} 가 {@code materialize()}
     *       를 부르기 전 단계이므로, 여기서 근거를 지우면 반영이 실패했을 때 되짚을
     *       원본이 없다.</li>
     * </ul>
     *
     * <p>통과하는 상태는 {@code MATERIALIZED}·{@code REJECTED}·{@code EXPIRED}·
     * {@code CANCELLED_BY_SENIOR} 넷뿐이다 — 전부 "이 후보는 끝났다"를 뜻한다.
     * {@link FactCandidateStatus} 에 새 값이 생기면 여기에 넣을지 <b>반드시</b> 판단해야
     * 한다. 빠뜨리면 그 상태의 후보를 가진 대화가 조용히 삭제 대상이 되므로, 테스트가
     * enum 전량을 훑어 판단을 강제한다.</p>
     */
    static final List<FactCandidateStatus> UNSETTLED = List.of(
        FactCandidateStatus.CAPTURED,
        FactCandidateStatus.NEEDS_CLARIFICATION,
        FactCandidateStatus.NEEDS_CONFIRMATION,
        FactCandidateStatus.COORDINATION_REQUIRED,
        FactCandidateStatus.CONFIRMED);

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository messageRepository;
    private final OnboardingAnswerRepository onboardingAnswerRepository;
    private final FactCandidateRepository factCandidateRepository;
    private final CareRecordRepository careRecordRepository;
    private final ConversationLifecycleProperties properties;
    private final Clock clock;

    /**
     * 대화 하나당 트랜잭션 하나, 직접 연다.
     *
     * <p><b>왜 {@code @Transactional} 을 {@link #purgeOne} 에 달지 않는가.</b>
     * {@link #purgeExpired()} 가 같은 빈 안에서 부르는 자기 호출이라 Spring 프록시를
     * 타지 않는다 — 애너테이션은 그 자리에 있고, 리뷰에서 올바르게 읽히고, 아무 일도
     * 하지 않는다. 트랜잭션 없이 참조 비우기와 발화 삭제가 따로 커밋되면 정확히 이
     * 서비스가 막으려는 상태(끊어진 참조)가 만들어진다.
     * {@code EmbeddingSyncService} 가 같은 함정을 이미 문서화했다.</p>
     *
     * <p><b>왜 배치 전체를 한 트랜잭션으로 묶지 않는가.</b> 대화 200개 삭제가
     * all-or-nothing 이면 한 행의 실패가 199개를 되돌리고, 다음 실행이 같은 200개를
     * 다시 시도해 같은 지점에서 또 멈춘다 — 영원히 한 건도 못 지운다.</p>
     */
    private final TransactionTemplate transactions;

    public ConversationRawPurgeService(
        ConversationRepository conversationRepository,
        ConversationMessageRepository messageRepository,
        OnboardingAnswerRepository onboardingAnswerRepository,
        FactCandidateRepository factCandidateRepository,
        CareRecordRepository careRecordRepository,
        ConversationLifecycleProperties properties,
        PlatformTransactionManager transactionManager,
        Clock clock
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.onboardingAnswerRepository = onboardingAnswerRepository;
        this.factCandidateRepository = factCandidateRepository;
        this.careRecordRepository = careRecordRepository;
        this.properties = properties;
        this.transactions = new TransactionTemplate(transactionManager);
        this.clock = clock;
    }

    /**
     * 한 번의 실행이 한 일. 스위퍼가 로그로 남기고 테스트가 단언한다.
     *
     * @param conversationsPurged 발화를 지운 대화 수
     * @param messagesDeleted 지운 발화 행 수
     * @param referencesCleared 비운 논리 참조 수(세 테이블 합계)
     * @param skipped 기능이 꺼져 있어 아무것도 하지 않았는가
     */
    public record PurgeReport(int conversationsPurged, int messagesDeleted,
                              int referencesCleared, boolean skipped) {

        /** 꺼져 있어서 아무 일도 하지 않은 실행. 0 건 실행과 구분된다. */
        static PurgeReport disabled() {
            return new PurgeReport(0, 0, 0, true);
        }
    }

    /** 대화 하나를 처리한 결과. */
    private record Purged(int messagesDeleted, int referencesCleared) {

        static final Purged NOTHING = new Purged(0, 0);

        boolean didSomething() {
            return messagesDeleted > 0 || referencesCleared > 0;
        }
    }

    /**
     * 만료됐고 선행조건을 전부 통과한 대화의 Raw 를 배치 상한만큼만 지운다.
     *
     * <p><b>멱등하다.</b> {@code findPurgeable} 의 "발화가 존재하는 대화만" 술어가 삭제
     * 완료 표시를 겸한다 — 지운 대화는 발화가 0건이 되어 다음 실행의 후보에서 자동으로
     * 빠진다. 그래서 {@code raw_purged_at} 같은 새 컬럼이 필요 없고, 따라서 <b>새 Flyway
     * 마이그레이션도 없다</b>. 두 인스턴스가 동시에 같은 대화를 잡아도 진 쪽의 삭제가
     * 0행을 돌려주고 참조 비우기가 no-op 이 되어 같은 상태로 수렴한다.</p>
     */
    public PurgeReport purgeExpired() {
        if (!properties.isPurgeEnabled()) {
            // 빈 조건부 생성(스위퍼)이 1차 방어지만, 서비스를 직접 부르는 경로 —
            // 운영 스크립트, 다른 컴포넌트, 테스트 — 까지 막는다. 되돌릴 수 없는
            // 동작의 스위치는 한 군데서만 지켜지면 안 된다.
            return PurgeReport.disabled();
        }

        OffsetDateTime now = OffsetDateTime.now(clock);
        PageRequest page = PageRequest.of(0, Math.max(1, properties.getPurgeBatchSize()));
        List<Conversation> due = conversationRepository.findPurgeable(now, UNSETTLED, page);

        int conversations = 0;
        int messages = 0;
        int references = 0;
        int failed = 0;
        for (Conversation conversation : due) {
            // 대화 하나의 실패가 배치 전체를 버리면 안 된다.
            //
            // findPurgeable 이 rawMessagesExpiresAt ASC 로 결정적으로 정렬하므로, 예외를
            // 밖으로 흘리면 같은 대화가 매 실행 맨 앞에 다시 오고 그 뒤 대화는 영원히
            // 지워지지 않는다. 더 나쁜 것은 그 상태가 정상으로 보인다는 점이다 —
            // 아래 countExpiredStillHoldingMessages 로그는 "선행조건에 막혀 남아 있다"고
            // 설명하므로 운영자는 막힌 것과 실패한 것을 구분할 수 없다. 그래서 실패는
            // 여기서 잡고 따로 센다. 형제 잡(DailyConversationSummaryService,
            // DailySummaryScheduler)도 같은 규약이다.
            try {
                Purged purged = purgeOne(conversation.getId());
                if (purged.didSomething()) {
                    conversations++;
                    messages += purged.messagesDeleted();
                    references += purged.referencesCleared();
                }
            } catch (RuntimeException error) {
                failed++;
                log.warn("conversation raw purge failed for conversation {}; the batch continues "
                    + "and the next run retries it", conversation.getId(), error);
            }
        }

        if (conversations > 0) {
            // 발화 원문은 싣지 않는다. 건수와 대화 수만 남긴다.
            log.info("conversation raw purge deleted {} utterance(s) from {} conversation(s) "
                + "and cleared {} evidence reference(s)", messages, conversations, references);
        }

        if (failed > 0) {
            // 실패는 "선행조건에 막혀 남았다"와 반드시 구분되어야 한다. 아래 잔류 수만
            // 보이면 운영자는 둘을 같은 것으로 읽는다.
            log.warn("conversation raw purge: {} conversation(s) failed this run", failed);
        }

        // 만료됐는데도 남아 있는 대화 수를 매번 드러낸다. 줄지 않고 평평하면 선행조건에
        // 영구히 막힌 대화(예: 요약이 생기지 않는 CANCELLED + 발화 있음)가 쌓이는 중이다.
        // 이 한 줄이 없으면 "무기한 보관"이 다시 아무에게도 보이지 않는 상태가 된다.
        long stillHeld = conversationRepository.countExpiredStillHoldingMessages(now);
        if (stillHeld > 0) {
            log.info("conversation raw purge: {} expired conversation(s) still hold utterances "
                + "(retained by a precondition; see ConversationRepository.findPurgeable)",
                stillHeld);
        }

        return new PurgeReport(conversations, messages, references, false);
    }

    /**
     * 대화 하나를 한 트랜잭션으로 처리한다.
     *
     * <p>순서는 아래 세 단계이며 <b>뒤집으면 복구할 수 없다</b>. 2단계를 3단계보다 먼저
     * 하는 이유는 "어느 id 를 비워야 하는지 알 수 있는 유일한 시점이 삭제 전"이기
     * 때문이다.</p>
     */
    private Purged purgeOne(UUID conversationId) {
        return transactions.execute(status -> {
            // 트랜잭션 안에서 활성 후보를 다시 확인한다. 배치 선별은 트랜잭션 밖에서
            // 한 번에 돌기 때문에, 선별과 이 시점 사이에 그 대화로 새 후보가 들어왔다면
            // 근거가 될 발화를 지우는 셈이 된다. 나머지 선행조건은 다시 보지 않는다 —
            // 만료 시각은 뒤로 가지 않고, 종료 상태는 OPEN 으로 되돌아가지 않으며
            // (openOrContinue 는 새 대화를 열지 기존 대화를 되살리지 않는다), 요약은
            // 사라지지 않는다. 즉 "지워도 됨 → 지우면 안 됨"으로 뒤집히는 조건은
            // 새 후보의 등장 하나뿐이다.
            if (factCandidateRepository.existsByConversationIdAndStatusIn(
                conversationId, UNSETTLED)) {
                log.info("conversation raw purge skipped conversation {}: an unsettled fact "
                    + "candidate appeared after the batch was selected", conversationId);
                return Purged.NOTHING;
            }

            // 1. 발화 id 만 읽는다. 본문은 메모리에 올리지 않는다 — 지우려는 내용을
            //    힙에(그리고 예외 로그에) 얹지 않기 위해서다.
            List<UUID> messageIds = messageRepository.findIdsByConversationId(conversationId);
            if (messageIds.isEmpty()) {
                // 다른 인스턴스가 먼저 지웠다. 오류가 아니라 수렴이다.
                return Purged.NOTHING;
            }

            // 지우려는 발화를 근거로 삼은 미정리 후보가 있는지 확인한다.
            //
            // ★ 위의 conversationId 확인만으로는 부족하다. 파괴 대상은 발화이고, 후보가
            //   그 발화를 지목하는 컬럼은 source_message_id 다. FactCandidate.recordEvidence
            //   가 두 값을 독립적으로 갱신하고 로봇 재질의 경로는 conversationId 만 보내므로,
            //   "대화 A 에서 생긴 후보가 대화 B 에서 재질의를 받아 conversationId 만 B 로
            //   옮겨가고 sourceMessageId 는 A 의 발화를 계속 가리키는" 상태가 정상적으로
            //   만들어진다. 그때 A 를 지우면 conversationId 확인은 통과하고, 바로 아래
            //   findBySourceMessageIdIn 이 그 후보를 찾아 근거를 지운 뒤 발화를 없앤다.
            //   아직 확인 대기 중인 복약 후보의 원본이 복구 불가능하게 사라진다.
            if (factCandidateRepository.existsByStatusInAndSourceMessageIdIn(
                UNSETTLED, messageIds)) {
                log.info("conversation raw purge skipped conversation {}: an unsettled fact "
                    + "candidate still cites one of its utterances as evidence", conversationId);
                return Purged.NOTHING;
            }

            // 2. 논리 참조를 먼저 비운다. 세 테이블 모두 물리 FK 가 없어 여기서 비우지
            //    않으면 끊어진 UUID 가 영구히 남는다(ERD §4, 검증 시나리오 31).
            //    이미 null 인 필드에 null 을 넣는 것은 no-op 이므로 재실행에 안전하다.
            int references = 0;
            for (OnboardingAnswer answer
                : onboardingAnswerRepository.findBySourceMessageIdIn(messageIds)) {
                answer.clearSourceMessage();
                references++;
            }
            for (FactCandidate candidate
                : factCandidateRepository.findBySourceMessageIdIn(messageIds)) {
                candidate.clearSourceMessage();
                references++;
            }
            for (CareRecord record : careRecordRepository.findBySourceMessageIdIn(messageIds)) {
                record.clearSourceMessage();
                references++;
            }

            // 3. 발화를 지운다. deleteByConversationId 의 flushAutomatically 가 위
            //    변경들을 이 DELETE 보다 먼저 기록하도록 강제한다. 둘은 같은
            //    트랜잭션이라 하나가 실패하면 둘 다 없던 일이 된다 — 참조만 비고 발화는
            //    남거나, 그 반대인 중간 상태로 끝나지 않는다.
            int deleted = messageRepository.deleteByConversationId(conversationId);
            return new Purged(deleted, references);
        });
    }
}
