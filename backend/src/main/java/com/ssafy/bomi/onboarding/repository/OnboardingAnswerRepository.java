package com.ssafy.bomi.onboarding.repository;

import com.ssafy.bomi.onboarding.domain.OnboardingAnswer;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OnboardingAnswerRepository extends JpaRepository<OnboardingAnswer, UUID> {

    /**
     * The current answer to one question of one session.
     *
     * <p>Answers are upserted, not appended (onboarding design note §1). Re-asking a
     * field must overwrite the previous attempt — if both rows survived, "which value is
     * current" would depend on read order.</p>
     */
    Optional<OnboardingAnswer> findBySessionIdAndQuestionCode(UUID sessionId, String questionCode);

    List<OnboardingAnswer> findBySessionId(UUID sessionId);

    /**
     * 주어진 발화들을 근거로 쓰는 답변들 (ERD §4, 검증 시나리오 31).
     *
     * <p>{@code ConversationRawPurgeService} 가 발화를 지우기 <b>직전에</b> 부른다.
     * 지금까지 이 테이블을 찾는 길은 {@code sessionId}/{@code questionCode} 뿐이라
     * "이 발화를 근거로 쓰는 행"을 찾을 방법이 아예 없었다 — 그래서 발화를 지우면
     * 존재하지 않는 행을 가리키는 UUID 가 조용히 남을 수밖에 없었다.</p>
     *
     * <p>삭제 <b>후</b>에는 이 조회가 성립하지 않는다. 물리 FK 도
     * {@code ON DELETE SET NULL} 도 없으므로(V1 주석), 되짚으려면 이 테이블 전량을 훑어
     * "{@code conversation_message} 에 없는 id"를 역으로 구해야 하는데, 그때는 다른
     * 대화의 살아 있는 발화와 구분할 방법이 이미 사라진 뒤다.</p>
     */
    List<OnboardingAnswer> findBySourceMessageIdIn(Collection<UUID> sourceMessageIds);
}
