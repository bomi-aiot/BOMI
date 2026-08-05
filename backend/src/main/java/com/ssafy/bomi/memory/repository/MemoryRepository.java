package com.ssafy.bomi.memory.repository;

import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MemoryRepository extends JpaRepository<Memory, UUID> {

    /**
     * 최근 기억 5건, 가시성 구분 없이.
     *
     * <p><b>가디언 화면에 그대로 쓰지 말 것 (S15P11E102-262 에서 발견된 결함).</b>
     * 이름과 옛 주석이 "가디언 대시보드용"이라 말하지만 이 쿼리는 lifecycle 만 걸러서
     * {@code visibility = PRIVATE} 인 기억도 그대로 돌려준다 — "이건 나만 알고
     * 있을래요"라고 답한 내용이 보호자 화면에 뜨는 경로가 이것이었다. 가디언이 보는
     * 화면은 반드시 {@link #findVisibleToGuardianBySeniorIdAndLifecycleStatus} 를 써야
     * 한다. 이 메서드는 로봇이 스스로에게 필요한 조회(가시성 무관)를 위해 남겨 둔다.</p>
     */
    List<Memory> findTop5BySeniorIdAndLifecycleStatusOrderByFirstObservedAtDesc(
            UUID seniorId, MemoryLifecycleStatus lifecycleStatus);

    /**
     * 가디언 화면에 노출해도 되는 최근 기억만 고른다 (S15P11E102-262).
     *
     * <p>{@code visibility IN (허용 목록)} 을 반드시 지정해야 한다 — {@link Memory#create}
     * 의 기본 가시성이 {@code PRIVATE} 이므로(§4, CLAUDE.md §9 의 T4), 이 필터가 빠지면
     * "혼자만 알고 싶다"고 답한 기억이 조용히 보호자 화면에 나타난다. {@link #findRetrievable}
     * 이 로봇-발화용 사전필터인 것처럼, 이 쿼리는 가디언 화면용 사전필터다.</p>
     */
    @Query("""
        SELECT m FROM Memory m
        WHERE m.seniorId = :seniorId
          AND m.lifecycleStatus = :lifecycleStatus
          AND m.visibility IN :allowedVisibilities
        ORDER BY m.firstObservedAt DESC
        """)
    List<Memory> findVisibleToGuardianBySeniorIdAndLifecycleStatus(
        @Param("seniorId") UUID seniorId,
        @Param("lifecycleStatus") MemoryLifecycleStatus lifecycleStatus,
        @Param("allowedVisibilities") Collection<MemoryVisibility> allowedVisibilities,
        Pageable pageable);

    /** 가디언 '대화 정보/기억' 화면용 — 한 어르신의 전체 기억(삭제 제외는 서비스에서). */
    List<Memory> findBySeniorIdOrderByFirstObservedAtDesc(UUID seniorId);

    /**
     * Every memory a given requester is allowed to see for one senior.
     *
     * <p>This query <strong>is</strong> the pre-filter the MVP ERD §4 specifies, and it
     * is a privacy and safety control rather than an optimisation:</p>
     * <ul>
     *   <li>{@code seniorId} — never mix two seniors' memories.</li>
     *   <li>{@code lifecycleStatus = ACTIVE} — a superseded fact is a fact that changed.
     *       Surfacing it makes the robot state something that is no longer true.</li>
     *   <li>{@code verificationStatus != REJECTED} — a rejected extraction was wrong.
     *       Often it was wrong because ASR mis-heard, so it is exactly the material
     *       that must never reach a prompt.</li>
     *   <li>{@code visibility IN (allowed)} — decided by who is asking. The robot
     *       talking to the senior may use {@code PRIVATE}; a guardian may not.</li>
     * </ul>
     *
     * <p>Ranking is deliberately absent. Similarity, importance, and recency are
     * combined by the assembly service, because the similarity half comes from an
     * external store and cannot be expressed in this query.</p>
     *
     * <p>Note for anyone adding a guardian-facing query here:
     * {@link #findTop5BySeniorIdAndLifecycleStatusOrderByFirstObservedAtDesc} filters only
     * by lifecycle and must never be used to build prompt context (it does not apply
     * visibility) — and, symmetrically, this method's ranking-only result set is not the
     * guardian pre-filter either. Guardian screens go through
     * {@link #findVisibleToGuardianBySeniorIdAndLifecycleStatus} (S15P11E102-262).</p>
     */
    @Query("""
        SELECT m FROM Memory m
        WHERE m.seniorId = :seniorId
          AND m.lifecycleStatus = com.ssafy.bomi.memory.domain.MemoryLifecycleStatus.ACTIVE
          AND m.verificationStatus <> com.ssafy.bomi.memory.domain.MemoryVerificationStatus.REJECTED
          AND m.visibility IN :allowedVisibilities
        """)
    List<Memory> findRetrievable(
        @Param("seniorId") UUID seniorId,
        @Param("allowedVisibilities") Collection<MemoryVisibility> allowedVisibilities);
    /**
     * Memories whose vector needs (re)building, oldest first (S15P11E102-218).
     *
     * <p><b>Paged, and the caller's page size is a spending cap.</b> Every row returned here
     * becomes one billed embedding call. An unpaged query would hand the sync job the entire
     * backlog and it would spend the whole API balance in one run.</p>
     *
     * <p>Only retrievable memories are worth embedding. A {@code SUPERSEDED} or
     * {@code REJECTED} memory can never be returned by {@link #findRetrievable}, so paying to
     * index it buys nothing — and a rejected extraction is usually a mis-heard sentence,
     * which is the last thing that should be findable by meaning.</p>
     *
     * <p>Oldest first so a permanently failing row cannot starve newer ones forever: it is
     * marked {@code FAILED}, and {@code FAILED} is only retried when the caller asks for it.</p>
     */
    @Query("""
        SELECT m FROM Memory m
        WHERE m.embeddingStatus IN :statuses
          AND m.lifecycleStatus = com.ssafy.bomi.memory.domain.MemoryLifecycleStatus.ACTIVE
          AND m.verificationStatus <> com.ssafy.bomi.memory.domain.MemoryVerificationStatus.REJECTED
        ORDER BY m.firstObservedAt ASC NULLS FIRST
        """)
    List<Memory> findNeedingEmbedding(
        @Param("statuses") Collection<EmbeddingStatus> statuses, Pageable pageable);

    /**
     * 이번 턴에 실제로 문맥에 실린 기억들의 {@code last_used_at} 을 한 번에 갱신한다
     * (S15P11E102-262).
     *
     * <p>왜 존재하는가 — {@link Memory#markUsed()} 는 이미 있었지만 아무도 호출하지
     * 않았다. 그 결과 "최근에 쓴 기억은 감점"하는 랭킹 규칙이 있어도 무엇이 최근에
     * 쓰였는지 아는 방법이 없어서 규칙 자체가 죽어 있었다.</p>
     *
     * <p>루프를 돌며 엔티티를 하나씩 저장하지 않고 벌크 UPDATE 를 쓴다 — 이 컬럼
     * 하나만 바뀌고 나머지 필드는 전혀 필요 없으므로, topK(3~10)개를 위해 엔티티를
     * 다시 로드할 이유가 없다(CLAUDE.md §18, Jetson 이 아니라 서버지만 습관을
     * 통일한다).</p>
     *
     * <p><b>{@code clearAutomatically = true} 가 필수다.</b> 벌크 UPDATE 는 JDBC 로
     * 직접 나가서 1차 캐시(영속성 컨텍스트)를 건드리지 않는다. 이 갱신 직후 같은
     * 트랜잭션 안에서 {@link #findRetrievable} 을 다시 호출하면(예: 같은 대화에서
     * 문맥을 두 번 조립) Hibernate 가 방금 갱신한 행도 캐시된 옛 엔티티를 그대로
     * 돌려줘 {@code last_used_at} 이 여전히 null 로 보인다 — 감점 규칙이 소리 없이
     * 죽는 결함이었다.</p>
     */
    @Modifying(clearAutomatically = true)
    @Query("UPDATE Memory m SET m.lastUsedAt = :usedAt WHERE m.id IN :ids")
    void markUsed(@Param("ids") Collection<UUID> ids, @Param("usedAt") OffsetDateTime usedAt);

    /**
     * Marks every synced row of one model stale (S15P11E102-218).
     *
     * <p>Used when the embedding model changes. A vector from a different model sits in a
     * different vector space, so its similarity scores are not merely worse — they are
     * meaningless, and they look like ordinary numbers.</p>
     *
     * <p>A bulk update rather than a loop because this touches every row and none of them
     * need an entity loaded. It costs no API calls; the re-embedding happens later, capped
     * per run.</p>
     */
    @Modifying
    @Query("""
        UPDATE Memory m
        SET m.embeddingStatus = com.ssafy.bomi.embedding.domain.EmbeddingStatus.STALE
        WHERE m.embeddingStatus = com.ssafy.bomi.embedding.domain.EmbeddingStatus.SYNCED
          AND (m.embeddingModel IS NULL OR m.embeddingModel <> :currentModel)
        """)
    int markStaleForOtherModels(@Param("currentModel") String currentModel);
}
