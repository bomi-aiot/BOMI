package com.ssafy.bomi.fact.repository;

import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactSourceType;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FactCandidateRepository extends JpaRepository<FactCandidate, UUID> {

    /**
     * 같은 어르신·같은 발화·같은 factType 으로 이미 제출된 후보가 있는지 찾는다
     * (S15P11E102-255). 로봇의 큐 flush 는 최소 한 번(at-least-once) 제출을 전제해
     * 네트워크 타임아웃 뒤 재시도가 이미 성공한 제출을 다시 보낼 수 있다 — 이 조회로
     * 같은 발화가 기억에 두 번 쌓이는 것을 막는다.
     */
    Optional<FactCandidate> findBySeniorIdAndSourceMessageIdAndFactType(
            UUID seniorId, UUID sourceMessageId, String factType);

    /** 하루 저장 건수 상한 판정에 쓴다(S15P11E102-255). 온보딩 답변 유입은 세지 않는다. */
    long countBySeniorIdAndSourceTypeAndCreatedAtAfter(
            UUID seniorId, FactSourceType sourceType, OffsetDateTime after);

    List<FactCandidate> findBySeniorIdAndStatusInOrderByCreatedAtDesc(
            UUID seniorId, Collection<FactCandidateStatus> statuses);

    long countBySeniorIdAndStatusIn(UUID seniorId, Collection<FactCandidateStatus> statuses);

    /**
     * Candidates the robot could raise in conversation, oldest first.
     *
     * <p>Oldest first so nothing starves. The caller then picks <b>exactly one</b> —
     * the ERD contract allows a single active candidate per conversation, and asking
     * about three pending facts at once breaks it (CLAUDE.md §12).</p>
     */
    List<FactCandidate> findBySeniorIdAndStatusInOrderByCreatedAtAsc(
            UUID seniorId, Collection<FactCandidateStatus> statuses);

    /**
     * "기억하지 마" — 한 대화에서 나온 미확정 후보 전부 (S15P11E102-348).
     *
     * <p>로봇은 서버가 배정한 후보 id 를 모르므로 취소의 단위는 대화다. 상태
     * 목록은 호출부(FactCandidateCancellationService)가 미확정 단계만 넘긴다.</p>
     */
    List<FactCandidate> findBySeniorIdAndConversationIdAndStatusIn(
            UUID seniorId, UUID conversationId, Collection<FactCandidateStatus> statuses);

    /**
     * The candidate produced by a given onboarding answer.
     *
     * <p>Answers are upserted, so their candidate is updated in place rather than
     * duplicated. Without this lookup, re-answering a question would leave the old
     * candidate behind and the senior would be asked about the same fact twice.</p>
     */
    Optional<FactCandidate> findByOnboardingAnswerId(UUID onboardingAnswerId);

    /**
     * 주어진 발화들을 근거로 쓰는 후보들 (ERD §4, 검증 시나리오 31).
     *
     * <p>{@code ConversationRawPurgeService} 가 발화를 지우기 <b>직전에</b> 부른다.
     * 삭제 후에는 어느 후보의 근거를 비워야 했는지 알 방법이 영원히 없다 — 물리 FK 도
     * {@code ON DELETE SET NULL} 도 없다(V1 주석).</p>
     *
     * <p>{@link #findBySeniorIdAndSourceMessageIdAndFactType} 로 대신할 수 없다.
     * 저쪽은 dedup 용이라 어르신과 factType 까지 알아야 하는데, 삭제 잡이 아는 것은
     * 발화 id 뿐이다.</p>
     */
    List<FactCandidate> findBySourceMessageIdIn(Collection<UUID> sourceMessageIds);

    /**
     * 이 대화에 아직 정리되지 않은 후보가 <b>하나라도</b> 있는가 (ERD §4).
     *
     * <p>{@code ConversationRawPurgeService} 가 대화별 트랜잭션 <b>안에서</b> 선행조건을
     * 다시 확인하는 데 쓴다. 배치 선별({@code ConversationRepository.findPurgeable})은
     * 트랜잭션 밖에서 한 번에 돌기 때문에, 선별과 실제 삭제 사이에 그 대화로 새 후보가
     * 들어오면 근거가 될 발화가 이미 사라진 뒤가 된다. 그 창을 닫는다.</p>
     *
     * <p>{@link #findBySeniorIdAndConversationIdAndStatusIn} 을 쓰지 않는 이유: 저쪽은
     * 행을 전부 로드한다. 여기서 알아야 하는 것은 "있나 없나" 하나뿐이고, 지우기 직전에
     * 불필요한 행을 메모리에 올릴 이유가 없다. 어르신 id 를 묻지 않는 것도 의도적이다 —
     * 다른 어르신의 후보가 이 대화에 달려 있다면 그것이야말로 지우면 안 되는 신호다.</p>
     */
    boolean existsByConversationIdAndStatusIn(
            UUID conversationId, Collection<FactCandidateStatus> statuses);

    /**
     * 이 <b>발화들</b>을 근거로 삼은 미정리 후보가 하나라도 있는가 (ERD §4).
     *
     * <p><b>왜 위 메서드로 부족한가.</b> 위쪽은 {@code conversation_id} 를 묻는데, Raw 삭제가
     * 실제로 파괴하는 것은 발화이고 후보가 그 발화를 지목하는 컬럼은 {@code source_message_id}
     * 다. 두 값은 {@link com.ssafy.bomi.fact.domain.FactCandidate#recordEvidence} 가 서로
     * 독립적으로 갱신하므로 갈라질 수 있다 — 로봇의 재질의 경로는 {@code conversationId} 만
     * 보내고 {@code sourceMessageId} 는 비워 두기 때문에, "대화 A 에서 생긴 후보가 대화 B 에서
     * 재질의를 받아 {@code conversationId} 만 B 로 옮겨간" 상태가 정상적으로 만들어진다.</p>
     *
     * <p>그 상태에서 A 가 만료되면 {@code conversation_id} 축 확인은 통과하고, 삭제 단계의
     * {@link #findBySourceMessageIdIn} 이 바로 그 후보를 찾아 근거를 지운 뒤 발화를 없앤다.
     * 아직 확인 대기 중인 후보의 원본이 복구 불가능하게 사라진다. 이 메서드가 그 경로를 막는
     * <b>실제 방어선</b>이고, 위 메서드는 더 보수적인 여분이다.</p>
     */
    boolean existsByStatusInAndSourceMessageIdIn(
            Collection<FactCandidateStatus> statuses, Collection<UUID> sourceMessageIds);
}
