package com.ssafy.bomi.user.repository;

import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.UserStatus;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AppUserRepository extends JpaRepository<AppUser, UUID> {

    /** Shared admission lock for every scenario started for one senior. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select u from AppUser u where u.id = :id")
    Optional<AppUser> findByIdForUpdate(@Param("id") UUID id);

    /** 단일 어르신 전제(P0): user_type = 'SENIOR' 인 첫 사용자. */
    Optional<AppUser> findFirstByUserType(String userType);

    /**
     * 그 유형의 사용자 전부, 항상 같은 순서로 (S15P11E102 G1 일간 요약).
     *
     * <p>{@link #findFirstByUserType} 만 있으면 "어르신은 한 명"이라는 P0 전제가 코드에
     * 못으로 박힌다. 일간 요약은 어르신마다 다른 시간대를 존중해야 하므로 — 서울이
     * 새벽 2시일 때 뉴욕은 낮 1시다 — 전원을 훑을 수 있어야 한다. 이 메서드가 없으면
     * 요약 배치는 첫 번째 어르신의 시간대로 모두를 재단하고, 나머지 어르신의 "하루"는
     * 조용히 어긋난 채 그럴듯하게 저장된다.</p>
     *
     * <p>정렬을 id 로 고정하는 것은 스윕의 지출 상한 때문이다 — 상한에 걸려 잘릴 때
     * 매 틱 같은 사람만 처리되고 뒤쪽 사람이 영원히 밀리는 일이 없도록, 최소한 순서가
     * 재현 가능해야 진단이 가능하다.</p>
     *
     * <p>{@code user_type} 에 인덱스는 없다. 매시간 한 번 도는 배치이고 MVP 규모(어르신
     * 소수)에서는 전체 스캔이 문제가 아니지만, 규모가 커지면 인덱스가 필요하다.</p>
     */
    List<AppUser> findByUserTypeOrderByIdAsc(String userType);

    /**
     * 그 유형의 <b>살아 있는</b> 사용자 전부, 항상 같은 순서로 (S15P11E102 G2 일일 요약
     * 발송).
     *
     * <p>{@link #findByUserTypeOrderByIdAsc} 와 나란히 두는 이유는 <b>탈퇴한 어르신</b>
     * 때문이다. {@code WITHDRAWN} 인 사람의 활동 요약이 계속 나가는 것은 낭비가 아니라
     * 사고이고, 그 사고는 아무 예외도 없이 매일 아침 조용히 반복된다. 그래서 조회 단계에서
     * 잘라 낸다 — 호출부의 {@code if} 문은 언젠가 빠뜨린다.</p>
     *
     * <p><b>정정 (리뷰 지적).</b> 이 자리에 원래 "요약 <em>생성</em>은 DB 안에서 끝나므로
     * {@code status} 를 안 봐도 조용한 낭비에 그친다"고 적혀 있었다. <b>틀렸다.</b> 생성
     * 경로({@code DailyConversationSummaryService})는 하루치 발화 원문을 프롬프트로 조립해
     * <b>외부 생성형 LLM 으로 보낸다.</b> 탈퇴한 어르신의 발화는 보존기간(기본 30일) 동안
     * 남으므로, 상태를 안 보면 탈퇴 후 30일 내내 그 사람의 대화 원문이 매일 밖으로 나간다.
     * 그것은 낭비가 아니라 처리 정지 위반이다. 그래서 <b>생성과 발송 둘 다</b> 이 메서드를
     * 쓴다.</p>
     *
     * <p>{@code SUSPENDED} 도 함께 빠진다. 정지된 계정에 대해 "지금 이 사람이 어떻게
     * 지내는지"를 계속 보내는 것은 정지의 의미와 어긋난다.</p>
     *
     * <p>정렬을 id 로 고정하는 이유는 위 메서드와 같다 — 순서가 재현 가능해야 "왜 이
     * 어르신만 요약이 안 왔나"를 로그로 추적할 수 있다.</p>
     */
    List<AppUser> findByUserTypeAndStatusOrderByIdAsc(String userType, UserStatus status);
}
