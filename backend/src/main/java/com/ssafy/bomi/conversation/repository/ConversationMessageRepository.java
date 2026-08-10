package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.ConversationMessage;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationMessageRepository extends JpaRepository<ConversationMessage, UUID> {

    /**
     * The tail of a conversation, newest first.
     *
     * <p>Ordered descending and paged so the query reads only the window the prompt
     * needs. Loading a whole conversation and slicing in memory would work today and
     * stop working the first time someone talks to the robot for an hour.</p>
     *
     * <p>The caller reverses the result before building the prompt: the model needs
     * chronological order, but the database needs to find the newest rows first.
     * {@code sequenceNo} breaks ties so two messages recorded in the same instant keep
     * the order they were actually said in.</p>
     */
    List<ConversationMessage> findByConversationIdOrderByOccurredAtDescSequenceNoDesc(
        UUID conversationId, Pageable pageable);

    /**
     * The highest sequence number used in a conversation, or null when it is empty.
     *
     * <p>The robot does not track sequence numbers. It would have to survive reboots and
     * stay in step with the app writing to the same conversation, and getting that wrong
     * reorders a transcript nobody would notice was wrong. The server owns the ordering;
     * the robot only says "this happened next".</p>
     */
    @Query("SELECT MAX(m.sequenceNo) FROM ConversationMessage m "
        + "WHERE m.conversationId = :conversationId")
    Integer findMaxSequenceNo(@Param("conversationId") UUID conversationId);

    /**
     * 이 대화에서 가장 최근 발화 시각, 또는 발화가 하나도 없으면 {@code null}
     * (S15P11E102-254).
     *
     * <p>{@code ConversationLifecycleService} 가 "마지막으로 무슨 일이 있었나"를
     * 판단하는 데 쓴다 — 발화가 있으면 그 시각이, 없으면 호출부가
     * {@code conversation.startedAt} 으로 대체한다. {@code findMaxSequenceNo} 와 같은
     * 이유로 서버가 계산한다: 로봇은 재시작을 버티며 정확한 순서를 유지할 필요가
     * 없다.</p>
     */
    @Query("SELECT MAX(m.occurredAt) FROM ConversationMessage m "
        + "WHERE m.conversationId = :conversationId")
    OffsetDateTime findMaxOccurredAt(@Param("conversationId") UUID conversationId);

    /**
     * 이 대화에 발화가 하나라도 있는가 (S15P11E102-254).
     *
     * <p>유휴시간 초과로 대화를 닫을 때 COMPLETED(발화 있음)와 CANCELLED(발화
     * 없음)를 가르는 데 쓴다 — 완료 조건이 명시적으로 요구하는 구분이다.</p>
     */
    boolean existsByConversationId(UUID conversationId);

    /**
     * One senior's messages within a time window.
     *
     * <p>Used by the daily aggregation. The subquery exists because {@code senior_id}
     * lives on {@code conversation}, not on the message — a message belongs to a
     * conversation, and only the conversation belongs to a person.</p>
     *
     * <p>The window is half-open ({@code >= from, < to}) so consecutive days never
     * double-count the midnight boundary.</p>
     */
    @Query("""
        SELECT m FROM ConversationMessage m
        WHERE m.conversationId IN (
            SELECT c.id FROM Conversation c WHERE c.seniorId = :seniorId)
          AND m.occurredAt >= :from AND m.occurredAt < :to
        """)
    List<ConversationMessage> findForSeniorBetween(
        @Param("seniorId") UUID seniorId,
        @Param("from") OffsetDateTime from,
        @Param("to") OffsetDateTime to);

    /**
     * 하루치 요약 프롬프트에 실을 발화 — 봉인되지 않은 대화의 것만, 최신순
     * (S15P11E102 G1).
     *
     * <p><b>{@link #findForSeniorBetween} 과 왜 따로 두는가.</b> 저쪽은 "몇 마디
     * 했는가"를 세는 지표용이라 봉인 여부를 가리지 않는 것이 맞다 — 어르신이 "우리끼리
     * 얘기"라고 한 대화도 그날 말을 한 건 사실이다. 반대로 이쪽은 원문을 그대로
     * 프롬프트로 조립한다. 봉인된 대화가 한 줄이라도 섞이면 그 내용이 요약문에 영구
     * 저장되고, 되먹임 경로({@code ConversationContextService.selectRelevantSummaries})를
     * 타고 로봇 입으로 되돌아온다. 저쪽 메서드에 {@code sealed = false} 를 얹어 하나로
     * 합치면 지표 쪽이 조용히 틀려지므로 반드시 나눈다.</p>
     *
     * <p>최신순 + 페이징인 이유는 {@link
     * #findByConversationIdOrderByOccurredAtDescSequenceNoDesc} 와 같다 — 페이지 크기가
     * 프롬프트 길이(=토큰 비용)의 상한이다. 하루는 대화 하나보다 훨씬 길 수 있어서
     * 상한 없이 읽으면 프롬프트 크기도 청구서도 예측 불가능해진다. 호출부가 시간순으로
     * 되뒤집는다.</p>
     *
     * <p>구간은 반열린 {@code [from, to)} — 자정 발화가 이틀에 두 번 실리지 않는다.</p>
     *
     * <p><b>왜 {@code sealed = false} 만으로 부족한가 — 열린 대화도 뺀다.</b> 봉인은
     * <b>종료 시점에만</b> 세워진다. {@code Conversation.markSealed()} 의 유일한 호출자가
     * {@code ConversationLifecycleService.end()} 이고, 유휴 자동 종료
     * ({@code closeIdleConversations})는 로봇의 봉인 판정을 알 방법이 없다. 그래서
     * {@code sealed = false} 는 "봉인되지 않았다"가 아니라 <b>"아직 봉인될 기회가 없었다"</b>
     * 일 수 있다.</p>
     *
     * <p>구체적으로: 어르신이 밤 11시에 "이건 우리끼리 얘기"라고 말한다. 로봇이 네트워크
     * 단절로 {@code POST /end(sealed=true)} 를 보내지 못한 채 자정을 넘긴다 — 아웃박스
     * 재시도 설계상 정상적으로 일어나는 상태다. 이 조건이 없으면 다음 날 새벽 배치가 그
     * 발화를 그대로 읽어 <b>외부 생성형 LLM 으로 보낸다.</b> 아침에 로봇이 재접속해
     * {@code sealed=true} 로 재전송해도 이미 늦고, 약속이 깨졌다는 사실은 어떤 로그에도
     * 남지 않는다. 대화 단위 요약({@code findNeedingSummary})은 {@code c.status IN :statuses}
     * 로 종료 대화만 보므로 원래 이 구멍이 없다 — 같은 방어를 여기에도 맞춘다.</p>
     */
    @Query("""
        SELECT m FROM ConversationMessage m
        WHERE m.conversationId IN (
            SELECT c.id FROM Conversation c
            WHERE c.seniorId = :seniorId
              AND c.sealed = false
              AND c.status <> com.ssafy.bomi.conversation.domain.ConversationStatus.OPEN)
          AND m.occurredAt >= :from AND m.occurredAt < :to
        ORDER BY m.occurredAt DESC, m.sequenceNo DESC
        """)
    List<ConversationMessage> findUnsealedForSeniorBetween(
        @Param("seniorId") UUID seniorId,
        @Param("from") OffsetDateTime from,
        @Param("to") OffsetDateTime to,
        Pageable pageable);

    /**
     * 이 대화에 속한 발화의 <b>id 만</b> (ERD §4, 보존기간 만료 삭제).
     *
     * <p><b>왜 엔티티가 아니라 id 인가.</b> 호출부가 필요한 것은 "어느 논리 참조를
     * 비워야 하는가" 하나뿐이다. 지우려고 불러온 발화 본문을 메모리에 올리는 것은
     * 낭비이자, 삭제 잡의 힙에 어르신의 대화 원문을 통째로 얹는 일이다 — 힙 덤프나
     * 예외 로그에 그것이 실려 나가면 "지웠다"는 약속과 어긋난다.</p>
     *
     * <p>{@code ConversationRawPurgeService} 가 삭제 <b>전에</b> 부른다. 삭제 후에는
     * 어느 id 를 비워야 했는지 알 방법이 영원히 없어진다(물리 FK 도
     * {@code ON DELETE SET NULL} 도 없다 — V1 주석).</p>
     */
    @Query("SELECT m.id FROM ConversationMessage m WHERE m.conversationId = :conversationId")
    List<UUID> findIdsByConversationId(@Param("conversationId") UUID conversationId);

    /**
     * 이 대화의 발화를 전부 <b>영구 삭제</b>한다 (ERD §4, 검증 시나리오 31·32).
     *
     * <p><b>저장소 전체에서 유일한 삭제 쿼리다.</b> 되돌릴 수 없다 —
     * {@code conversation_message} 에는 백업도 소프트 삭제도 감사 테이블도 없다. 반드시
     * {@code ConversationRawPurgeService} 를 통해서만 부른다. 그 서비스가 선행조건 판정
     * (ERD §4 네 가지)과 논리 참조 비우기를 <b>먼저</b> 끝낸다.</p>
     *
     * <p><b>{@code clearAutomatically} 가 없으면 무엇이 깨지는가.</b> 벌크 DELETE 는
     * JPQL 이 곧장 SQL 로 나가 영속성 컨텍스트를 우회한다. 1차 캐시에 남은 발화
     * 엔티티는 이미 지워진 행을 그대로 들고 있어서, 같은 트랜잭션의 후속 조회가 DB 에
     * 없는 발화를 되돌려준다. {@code flushAutomatically} 는 그 반대편을 막는다 —
     * 호출부가 방금 비운 논리 참조(dirty 상태)가 DELETE 보다 <b>먼저</b> 기록되도록
     * 강제한다. 같은 이유가 {@code MemoryRepository.markUsed} 에 이미 적혀 있다.</p>
     *
     * @return 실제로 지운 행 수. 0 이면 다른 인스턴스가 먼저 지웠다는 뜻이고, 그것은
     *     오류가 아니라 수렴이다.
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("DELETE FROM ConversationMessage m WHERE m.conversationId = :conversationId")
    int deleteByConversationId(@Param("conversationId") UUID conversationId);
}
