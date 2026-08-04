package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationRepository extends JpaRepository<Conversation, UUID> {

    /**
     * 지금 열려 있는 대화들 (S15P11E102-254).
     *
     * <p>{@code ConversationLifecycleSweeper} 가 주기적으로 훑어 유휴시간을 넘긴
     * 대화를 닫는다. 이 어르신용 로봇은 한 대뿐이라 동시에 OPEN 인 대화 수가 아주
     * 작다고 가정한다 — 그래서 대화별로 마지막 발화 시각을 따로 조회하는 N+1 이
     * 여기서는 문제가 아니다(정확한 최근 발화 시각을 correlated subquery 로 억지로
     * 한 번에 묶는 것보다 읽기 쉽다).</p>
     */
    List<Conversation> findByStatus(ConversationStatus status);

    /**
     * 요약이 아직 없는, 닫힌 대화들 (S15P11E102-254).
     *
     * <p>세 조건 전부를 만족해야 후보다.</p>
     * <ul>
     *   <li>{@code status} 가 요약할 가치가 있는 종료 상태다 (CANCELLED 는 발화가
     *       하나도 없던 대화라 요약할 내용이 없다 — 호출부가 상태 집합으로 이미
     *       뺀다).</li>
     *   <li>{@code sealed = false} — 봉인된 대화는 원문을 외부 LLM 에 보내지
     *       않는다(CLAUDE.md §9 T4).</li>
     *   <li>발화가 실제로 하나 이상 있다 — 상태만으로는 "닫혔지만 메시지가 없는"
     *       경계 사례를 못 거른다.</li>
     *   <li>아직 supersede 되지 않은 요약이 없다 — 이 조건이 "같은 스윕을 두 번
     *       돌려도 요약이 중복 생성되지 않는다"(완료 조건)를 쿼리 단에서 구조적으로
     *       보장한다. 두 번째 스윕이 도는 시점엔 이미 요약이 생겼으므로 후보에서
     *       빠진다.</li>
     * </ul>
     *
     * <p>{@code pageable} 은 {@code LlmProperties.maxCallsPerRun} 을 그대로 받는다 —
     * 한 행 = 과금 호출 1회이므로 이것은 튜닝이 아니라 지출 상한이다.</p>
     */
    @Query("""
        SELECT c FROM Conversation c
        WHERE c.status IN :statuses
          AND c.sealed = false
          AND EXISTS (
              SELECT 1 FROM ConversationMessage m WHERE m.conversationId = c.id)
          AND NOT EXISTS (
              SELECT 1 FROM ConversationSummary s
              WHERE s.conversationId = c.id AND s.supersededById IS NULL)
        ORDER BY c.endedAt ASC
        """)
    List<Conversation> findNeedingSummary(
        @Param("statuses") Collection<ConversationStatus> statuses, Pageable pageable);
}
