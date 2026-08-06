package com.ssafy.bomi.conversation.application;

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
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 닫힌 대화를 모아 요약을 만들고 저장한다 — 이 대화 요약 파이프라인의 "수원(생성 쪽)"
 * (S15P11E102-254).
 *
 * <p>어디에 위치하는가
 *     {@code ConversationSummaryScheduler} 가 주기적으로 {@link #summarizeDue()} 를
 *     부른다. 되먹임 배관({@code ConversationContextService.loadConversationSummary},
 *     {@code selectRelevantSummaries})은 이미 있다 — 이 서비스가 채우는 것은 그 배관이
 *     읽을 {@code conversation_summary} 행 자체다.</p>
 *
 * <p><b>LLM 호출은 반드시 트랜잭션 밖에서 실행한다.</b> Hikari 기본 풀은 커넥션 10개다.
 * 요약 하나에 몇 초가 걸리는 생성 호출을 트랜잭션 안에서 하면 그동안 커넥션 하나가
 * 잡혀 있고, 그 시간 동안 문맥 조립(턴 경로, ~2초 예산) 이 그 커넥션을 기다릴 수
 * 있다. 그래서 이 서비스는 "짧은 트랜잭션으로 읽기 → 트랜잭션 밖에서 생성 호출 →
 * 짧은 트랜잭션으로 쓰기" 세 단계로 나눈다. {@code EmbeddingSyncService} 가 임베딩
 * 호출을 트랜잭션 안에 넣는 것과는 의도적으로 다르다 — 임베딩은 1.2초 타임아웃으로
 * 짧고, 생성은 초 단위로 훨씬 길다.</p>
 */
@Service
public class ConversationSummaryService {

    private static final Logger log = LoggerFactory.getLogger(ConversationSummaryService.class);

    /**
     * 요약할 가치가 있는 종료 상태. CANCELLED(발화 없이 닫힘)는 뺀다 — 요약할 내용
     * 자체가 없다.
     */
    private static final Set<ConversationStatus> SUMMARIZABLE =
        EnumSet.of(ConversationStatus.COMPLETED, ConversationStatus.FAILED);

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository messageRepository;
    private final ConversationSummaryRepository summaryRepository;
    private final TextGenerator textGenerator;
    private final LlmProperties properties;
    private final TransactionTemplate transactions;

    public ConversationSummaryService(
        ConversationRepository conversationRepository,
        ConversationMessageRepository messageRepository,
        ConversationSummaryRepository summaryRepository,
        TextGenerator textGenerator,
        LlmProperties properties,
        PlatformTransactionManager transactionManager
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.summaryRepository = summaryRepository;
        this.textGenerator = textGenerator;
        this.properties = properties;
        this.transactions = new TransactionTemplate(transactionManager);
    }

    /** 한 번의 스윕이 한 일. 스케줄러가 로그로 남기고, 테스트가 단언할 수 있다. */
    public record SweepReport(int summarized, int failed, boolean skipped) {

        static SweepReport unavailable() {
            return new SweepReport(0, 0, true);
        }
    }

    /**
     * 요약이 없는 닫힌 대화를, {@code maxCallsPerRun} 만큼만 요약한다.
     *
     * <p>실패한 개별 대화는 건너뛰고 계속 진행한다 — 한 대화의 LLM 실패가 나머지
     * 배치를 막으면 안 된다(완료 조건: "LLM 호출이 실패해도 대화는 정상적으로 닫히고
     * 어르신과의 턴은 영향을 받지 않는다" — 이 스윕이 이미 닫힌 대화를 다루는
     * 쪽이므로, 실패해도 대화의 닫힘 상태 자체는 건드리지 않는다).</p>
     */
    public SweepReport summarizeDue() {
        if (!textGenerator.isAvailable()) {
            log.debug("conversation summary sweep skipped: llm generation unavailable");
            return SweepReport.unavailable();
        }

        PageRequest page = PageRequest.of(0, Math.max(1, properties.getMaxCallsPerRun()));
        List<Conversation> due = conversationRepository.findNeedingSummary(SUMMARIZABLE, page);

        int summarized = 0;
        int failed = 0;
        for (Conversation conversation : due) {
            if (summarizeOne(conversation.getId())) {
                summarized++;
            } else {
                failed++;
            }
        }
        if (summarized + failed > 0) {
            log.info("conversation summary sweep: {} summarized, {} failed "
                    + "({} billed calls, cap {})",
                summarized, failed, summarized + failed, properties.getMaxCallsPerRun());
        }
        return new SweepReport(summarized, failed, false);
    }

    private boolean summarizeOne(UUID conversationId) {
        Prepared prepared = transactions.execute(status -> prepare(conversationId));
        if (prepared == null) {
            return false;
        }

        String content;
        try {
            content = textGenerator.generate(buildPrompt(prepared));
        } catch (RuntimeException error) {
            log.warn("conversation summary generation failed; the conversation stays closed "
                    + "and untouched, the next sweep will retry: conversationId={}",
                conversationId, error);
            return false;
        }

        Boolean saved = transactions.execute(status -> saveSummary(conversationId, prepared, content));
        return Boolean.TRUE.equals(saved);
    }

    /** 요약에 필요한 원자료를 짧은 트랜잭션 안에서 한 번에 읽는다. */
    private Prepared prepare(UUID conversationId) {
        Conversation conversation = conversationRepository.findById(conversationId).orElse(null);
        if (conversation == null) {
            // 조회와 처리 사이에 다른 경로가 이미 지웠을 리는 없지만(삭제 기능 없음),
            // 방어적으로 조용히 건너뛴다.
            return null;
        }
        List<ConversationMessage> newestFirst = messageRepository
            .findByConversationIdOrderByOccurredAtDescSequenceNoDesc(
                conversationId, PageRequest.of(0, properties.getMaxSummaryMessages()));
        if (newestFirst.isEmpty()) {
            // findNeedingSummary 가 이미 걸렀어야 하지만, 방어적으로 한 번 더 본다.
            return null;
        }

        // Math.clamp/List.reversed() 는 Java 21 부터다. 이 프로젝트 툴체인은 17 이라
        // (ConversationContextService.loadRecentMessages 참고) 직접 뒤집는다.
        List<ConversationMessage> chronological = new ArrayList<>(newestFirst.size());
        for (int index = newestFirst.size() - 1; index >= 0; index--) {
            chronological.add(newestFirst.get(index));
        }
        OffsetDateTime periodStart = conversation.getStartedAt() != null
            ? conversation.getStartedAt() : chronological.get(0).getOccurredAt();
        OffsetDateTime periodEnd = conversation.getEndedAt() != null
            ? conversation.getEndedAt() : chronological.get(chronological.size() - 1).getOccurredAt();

        return new Prepared(conversation.getSeniorId(), periodStart, periodEnd, chronological);
    }

    /**
     * 요약을 저장한다. 이미 요약이 있으면(동시에 도는 스윕 등) 조용히 건너뛴다.
     *
     * <p>왜 재생성을 시도하지 않는가 — {@code conversation_summary} 의
     * {@code UNIQUE(senior_id, summary_type, period_started_at, period_ended_at)} 은
     * 이 대화의 기간(시작·종료 시각)이 고정값이라 두 번째 행을 절대 허용하지 않는다.
     * {@code supersededById} 체인은 기간이 달라지는 재생성(예: DAILY 요약이 나중에
     * 다시 도는 경우)을 위한 장치이지, 같은 대화를 다시 요약하는 경우를 위한
     * 것이 아니다 — {@link ConversationRepository#findNeedingSummary} 가 이미 요약이
     * 있는 대화를 후보에서 빼므로, 이 분기는 스윕이 겹쳐 도는 드문 경쟁 상황을 위한
     * 방어선일 뿐이다.</p>
     */
    private boolean saveSummary(UUID conversationId, Prepared prepared, String content) {
        Optional<ConversationSummary> existing =
            summaryRepository.findByConversationIdAndSupersededByIdIsNull(conversationId);
        if (existing.isPresent()) {
            log.debug("conversation {} already has a summary; skipping (concurrent sweep?)",
                conversationId);
            return false;
        }

        ConversationSummary summary = ConversationSummary.forConversation(
            prepared.seniorId(), conversationId, prepared.periodStart(), prepared.periodEnd(),
            content, prepared.messages().size());
        summaryRepository.save(summary);
        return true;
    }

    /**
     * 요약 프롬프트를 조립한다.
     *
     * <p>Prompts are code — 목적: 미래의 로봇이 "지난 대화"로 참고할 수 있게 사실만
     * 3문장 이내로 압축한다. 어느 저장소가 먹는가: 이 문자열의 결과물이
     * {@code conversation_summary.content} 로 저장되고, 로봇 쪽
     * {@code prompts/builder.py} 의 "지난 대화" 섹션이 그대로 읽는다. 예상 출력 모양:
     * 존댓말 평서문 2~3문장, 목록·번호 없음.</p>
     */
    private String buildPrompt(Prepared prepared) {
        StringBuilder transcript = new StringBuilder();
        for (ConversationMessage message : prepared.messages()) {
            String speaker = message.getRole() == MessageRole.SENIOR ? "어르신" : "로봇";
            transcript.append(speaker).append(": ").append(message.getContent()).append('\n');
        }
        return """
            다음은 돌봄 로봇과 어르신이 나눈 대화입니다. 이 대화를 로봇이 다음에 만났을 때 \
            참고할 수 있도록 두세 문장으로 요약하세요.
            - 대화에 실제로 있었던 내용만 쓰고, 없는 내용을 지어내지 마세요.
            - 진단이나 의학적 판단을 내리지 마세요.
            - 존댓말 평서문으로, 목록이나 번호 없이 문장으로만 쓰세요.

            대화:
            %s
            """.formatted(transcript.toString().strip());
    }

    /** 프롬프트 조립과 저장에 필요한, 한 번의 읽기 트랜잭션에서 모은 값들. */
    private record Prepared(
        UUID seniorId,
        OffsetDateTime periodStart,
        OffsetDateTime periodEnd,
        List<ConversationMessage> messages) {
    }
}
