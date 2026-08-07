package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
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

    /** Resolves the owning Scenario without attaching a stale Conversation before locking. */
    @Query("select c.scenarioId from Conversation c where c.id = :id")
    Optional<UUID> findScenarioIdById(@Param("id") UUID id);

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

    /**
     * 원본 발화를 <b>영구 삭제</b>해도 되는 대화들, 만료가 오래된 순 (ERD §4, 시나리오 32).
     *
     * <p><b>왜 선행조건을 전부 SQL 술어로 쓰는가.</b> 서비스에서 걸러내면
     * {@code pageable} 이 "지운 수"가 아니라 "검사한 수"의 상한이 된다 — 상한이 상한이
     * 아니게 되고, 되돌릴 수 없는 잡에서 그 차이는 사고의 폭이다. 그래서 ERD §4 의 네
     * 조건을 하나도 빠짐없이 여기서 표현한다.</p>
     *
     * <table border="1">
     *   <caption>ERD §4 선행조건 → 술어</caption>
     *   <tr><th>선행조건</th><th>술어</th><th>없으면 무엇이 조용히 깨지는가</th></tr>
     *   <tr>
     *     <td>보존기간 만료</td>
     *     <td>{@code rawMessagesExpiresAt IS NOT NULL AND <= :now}</td>
     *     <td>{@code NULL} 은 "만료 시각을 모른다"이지 "만료됐다"가 아니다(모르는 것과
     *         0 은 다르다). 이 술어가 없으면 아직 안 닫힌 대화와, 만료 시각을 채우는
     *         경로가 생기기 전에 만들어진 구버전 행이 통째로 삭제 대상이 된다.</td>
     *   </tr>
     *   <tr>
     *     <td>필요한 요약 생성</td>
     *     <td>{@code sealed = true OR EXISTS(현행 요약)}</td>
     *     <td>요약은 발화를 지운 뒤 남는 <b>유일한</b> 기록이다. 요약 없이 지우면 그날
     *         무슨 얘기를 했는지가 이 세상에서 사라진다. {@code sealed} 분기는 아래
     *         설명 참고 — 그것이 없으면 정반대로 가장 민감한 발화만 영구 보존된다.</td>
     *   </tr>
     *   <tr>
     *     <td>활성 후보 해소 + 확정 사실의 최종 반영</td>
     *     <td>{@code NOT EXISTS(...)} <b>두 개</b> — {@code conversationId} 축과
     *         {@code sourceMessageId} 축</td>
     *     <td>아직 확인 중이거나(4개 미확정 상태) 굳었지만 최종 테이블에 안 들어간
     *         ({@code CONFIRMED}) 후보의 근거 발화를 지우면, 반영이 실패했을 때
     *         되짚을 원본이 없다. 두 조건을 한 술어로 합친 이유는 호출부의 상수 주석
     *         참고.</td>
     *   </tr>
     *   <tr>
     *     <td>(방어) 열린 대화 제외</td>
     *     <td>{@code status <> OPEN}</td>
     *     <td>OPEN 대화에 만료 시각이 채워지는 경로는 지금 없지만, 대화가 진행 중인데
     *         그 발화가 사라지는 것은 어떤 버그로도 일어나선 안 되는 일이다.</td>
     *   </tr>
     *   <tr>
     *     <td>(멱등) 발화가 남아 있는 대화만</td>
     *     <td>{@code EXISTS(ConversationMessage)}</td>
     *     <td>이 술어가 삭제 완료 표시를 <b>겸한다</b> — 지운 대화는 발화가 0건이 되어
     *         다음 실행의 후보에서 자동으로 빠진다. 덕분에 {@code raw_purged_at} 같은
     *         새 컬럼이 필요 없고, 따라서 새 Flyway 마이그레이션도 없다.</td>
     *   </tr>
     * </table>
     *
     * <p><b>{@code sealed = true} 를 요약 없이 통과시키는 이유.</b>
     * {@link #findNeedingSummary} 가 {@code sealed = false} 로 봉인 대화를 요약 대상에서
     * 제외한다 — 봉인 대화의 요약은 "아직 안 만들어진" 것이 아니라 <b>만들면 안 되는</b>
     * 것이다. "요약 있어야 지운다"를 그대로 적용하면 봉인 대화의 Raw 는 영원히 남고,
     * 그 결과가 정확히 정반대다: 어르신이 "우리끼리 얘기"라고 말한 가장 민감한 발화만
     * 평문으로 영구 보존된다. ERD 문구가 "<b>필요한</b> 요약 생성"인 것을 그대로 읽으면,
     * 요약이 필요하지 않은 대화에서 이 조건은 공허하게 충족된다.</p>
     *
     * <p><b>왜 활성 후보를 두 축으로 두 번 보는가.</b> 이 잡이 실제로 파괴하는 것은
     * <b>발화</b>이고, 그 발화를 근거로 지목하는 컬럼은 {@code fact_candidate.source_message_id}
     * 다. 그런데 {@code conversation_id} 축만 보면 두 값이 갈라진 후보를 놓친다 —
     * {@code FactCandidate.recordEvidence} 가 두 값을 <b>독립적으로</b> 갱신하고, 로봇의
     * 재질의 경로({@code graph/handlers.py})는 {@code conversationId} 만 보내고
     * {@code sourceMessageId} 는 보내지 않는다. 그래서 "대화 A 에서 생긴 미확정 후보가
     * 대화 B 에서 재질의를 받으면 {@code conversationId} 만 B 로 옮겨가고
     * {@code sourceMessageId} 는 A 의 발화를 계속 가리키는" 상태가 정상적으로 만들어진다.
     *
     * <p>그 상태에서 A 가 만료되면 {@code conversation_id} 축 술어는 "A 를 가리키는 미확정
     * 후보가 없다"며 통과시키고, 삭제 단계는 {@code findBySourceMessageIdIn} 으로 바로 그
     * 후보를 찾아 근거를 지운 뒤 발화를 없앤다. <b>아직 확인 대기 중인 복약 후보의 원본
     * 발화가 선행조건을 만족한 채 사라진다.</b> 백업도 소프트삭제도 감사 테이블도 없어
     * 복구 경로가 없다. 그래서 두 술어를 모두 둔다 — {@code conversation_id} 축은 더
     * 보수적인 여분이고, <b>{@code sourceMessageId} 축이 실제 방어선</b>이다.</p>
     *
     * <p>만료가 오래된 순으로 정렬해 배치 상한에 걸린 잔여분이 굶지 않게 한다.</p>
     */
    @Query("""
        SELECT c FROM Conversation c
        WHERE c.rawMessagesExpiresAt IS NOT NULL
          AND c.rawMessagesExpiresAt <= :now
          AND c.status <> com.ssafy.bomi.conversation.domain.ConversationStatus.OPEN
          AND EXISTS (
              SELECT 1
              FROM ConversationMessage m
              WHERE m.conversationId = c.id
          )
          AND (
              c.sealed = true
              OR EXISTS (
                  SELECT 1
                  FROM ConversationSummary s
                  WHERE s.conversationId = c.id
                    AND s.supersededById IS NULL
              )
          )
          AND NOT EXISTS (
              SELECT 1
              FROM FactCandidate f
              WHERE f.conversationId = c.id
                AND f.status IN :unsettled
          )
          AND NOT EXISTS (
              SELECT 1
              FROM FactCandidate f2
              WHERE f2.status IN :unsettled
                AND f2.sourceMessageId IN (
                    SELECT m2.id
                    FROM ConversationMessage m2
                    WHERE m2.conversationId = c.id
                )
          )
        ORDER BY c.rawMessagesExpiresAt ASC
        """)
    List<Conversation> findPurgeable(
        @Param("now") OffsetDateTime now,
        @Param("unsettled") Collection<FactCandidateStatus> unsettled,
        Pageable pageable
    );

    /**
     * 보존기간이 지났는데도 아직 발화를 들고 있는 대화 수 (ERD §4).
     *
     * <p><b>왜 세는가.</b> {@link #findPurgeable} 은 선행조건을 통과한 것만 돌려주므로,
     * 통과하지 못해 영원히 남는 대화는 어떤 로그에도 나타나지 않는다. 실제로 그런 조합이
     * 있다 — {@code CANCELLED} 인데 발화가 남은 대화는 {@code ConversationSummaryService}
     * 의 요약 대상({@code COMPLETED}/{@code FAILED})이 아니라 요약이 영영 생기지 않고,
     * 그래서 영영 지워지지 않는다. 지우는 쪽이 아니라 남기는 쪽 오차라 그대로 두지만,
     * <b>드러나지 않는 무기한 보관</b>은 그 자체가 이 잡이 막으려는 문제다.</p>
     *
     * <p>이 수가 매 실행 줄어들면 정상이고, 0 이 아닌 값에서 평평해지면 위 같은 이유로
     * 막힌 대화가 쌓이고 있다는 뜻이다. 실행당 한 번 도는 count 하나이므로 값싸다.</p>
     */
    @Query("""
        SELECT count(c) FROM Conversation c
        WHERE c.rawMessagesExpiresAt IS NOT NULL
          AND c.rawMessagesExpiresAt <= :now
          AND EXISTS (
              SELECT 1
              FROM ConversationMessage m
              WHERE m.conversationId = c.id
          )
        """)
    long countExpiredStillHoldingMessages(@Param("now") OffsetDateTime now);
}
