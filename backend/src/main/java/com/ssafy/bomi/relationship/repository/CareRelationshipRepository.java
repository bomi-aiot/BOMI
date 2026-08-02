package com.ssafy.bomi.relationship.repository;

import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipStatus;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CareRelationshipRepository extends JpaRepository<CareRelationship, UUID> {

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
}
