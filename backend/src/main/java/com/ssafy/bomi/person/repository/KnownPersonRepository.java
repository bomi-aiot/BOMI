package com.ssafy.bomi.person.repository;

import com.ssafy.bomi.person.domain.KnownPerson;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface KnownPersonRepository extends JpaRepository<KnownPerson, UUID> {

    /**
     * 한 어르신의 명부 전체. 회피 여부 필터는 여기서 하지 않고 호출부
     * ({@code ConversationContextService})에서 한다 — "누가 회피 대상인가"는
     * 조회 조건이 아니라 도메인 규칙({@link KnownPerson#isAvoidTarget()})이고,
     * 쿼리 파생 메서드 이름으로 TRUE/NULL 합집합을 표현하면 오히려 읽기 어렵다.
     */
    List<KnownPerson> findBySeniorId(UUID seniorId);
}
