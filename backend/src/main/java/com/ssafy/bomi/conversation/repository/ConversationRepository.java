package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import jakarta.persistence.LockModeType;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationRepository extends JpaRepository<Conversation, UUID> {

    Optional<Conversation> findByScenarioId(UUID scenarioId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select c from Conversation c where c.id = :id")
    Optional<Conversation> findByIdForUpdate(@Param("id") UUID id);

    List<Conversation>
    findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNullAndStartedAtLessThanEqual(
        ConversationStatus status,
        OffsetDateTime cutoff
    );

    List<Conversation>
    findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNotNullAndAiStartedAtLessThanEqual(
        ConversationStatus status,
        OffsetDateTime cutoff
    );

    /**
     * 지금 열려 있는 대화들 (S15P11E102-254).
     *
     * <p>{@code ConversationLifecycleSweeper}가 주기적으로 훑어 유휴시간을 넘긴
     * 대화를 닫는다. 이 어르신용 로봇은 한 대뿐이라 동시에 OPEN인 대화 수가 아주
     * 작다고 가정한다.</p>
     */
    List<Conversation> findByStatus(ConversationStatus status);

    /**
     * 요약이 아직 없는, 닫힌 대화들 (S15P11E102-254).
     *
     * <p>다음 조건을 모두 만족하는 대화만 조회한다.</p>
     * <ul>
     *   <li>요약 대상 종료 상태에 해당한다.</li>
     *   <li>{@code sealed = false}이다.</li>
     *   <li>발화가 하나 이상 존재한다.</li>
     *   <li>아직 유효한 요약이 존재하지 않는다.</li>
     * </ul>
     *
     * <p>{@code pageable}은 한 번에 처리할 LLM 호출 수의 상한으로 사용한다.</p>
     */
    @Query("""
        SELECT c FROM Conversation c
        WHERE c.status IN :statuses
          AND c.sealed = false
          AND EXISTS (
              SELECT 1
              FROM ConversationMessage m
              WHERE m.conversationId = c.id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM ConversationSummary s
              WHERE s.conversationId = c.id
                AND s.supersededById IS NULL
          )
        ORDER BY c.endedAt ASC
        """)
    List<Conversation> findNeedingSummary(
        @Param("statuses") Collection<ConversationStatus> statuses,
        Pageable pageable
    );
}
