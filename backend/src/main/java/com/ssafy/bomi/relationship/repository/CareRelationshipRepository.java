package com.ssafy.bomi.relationship.repository;

import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.domain.RelationshipStatus;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CareRelationshipRepository extends JpaRepository<CareRelationship, UUID> {

    /** 보호자 헤더가 필요한 값만 읽는 경량 뷰. */
    interface PrimaryGuardianView {
        UUID getId();

        String getName();

        String getPriority();
    }

    /**
     * The live link between a senior and one guardian, if there is one.
     *
     * <p>Filtering on status here is the point of the method. A {@code PENDING},
     * {@code ENDED}, or {@code REVOKED} relationship must grant nothing — an ended
     * guardian who can still read shared memories is a privacy incident, and the
     * absence of this filter is the easiest way to cause one.</p>
     */
    Optional<CareRelationship> findBySeniorIdAndGuardianIdAndStatus(
        UUID seniorId, UUID guardianId, RelationshipStatus status);

    /**
     * The guardian a notification should reach.
     *
     * <p>Both T1 alerts and T2 summaries need a recipient, and "the primary guardian" is
     * the answer for both. Returns empty when nobody is connected — which is a real state
     * for a senior mid-onboarding, and the caller must handle it rather than assume.</p>
     */
    Optional<CareRelationship> findFirstBySeniorIdAndPriorityAndStatus(
        UUID seniorId, RelationshipPriority priority, RelationshipStatus status);

    /**
     * 활성 PRIMARY 관계와 실제 계정을 한 번에 확인한다.
     *
     * <p>대시보드는 이름 하나를 위해 관계 엔티티와 사용자 엔티티를 차례로 적재하지
     * 않는다. 연결 행이 존재하지만 계정이 없으면 결과도 없으므로 화면이 존재하지 않는
     * 보호자를 만들어 내지 않는 기존 계약은 그대로다.</p>
     */
    @Query(value = """
        SELECT guardian.id AS id,
               COALESCE(NULLIF(guardian.preferred_name, ''), guardian.name) AS name,
               relationship.priority AS priority
        FROM care_relationship relationship
        JOIN app_user guardian ON guardian.id = relationship.guardian_id
        WHERE relationship.senior_id = :seniorId
          AND relationship.priority = 'PRIMARY'
          AND relationship.status = 'ACTIVE'
          AND guardian.status = 'ACTIVE'
        ORDER BY relationship.connected_at DESC, relationship.id
        LIMIT 1
        """, nativeQuery = true)
    Optional<PrimaryGuardianView> findActivePrimaryGuardian(
        @Param("seniorId") UUID seniorId);
}
