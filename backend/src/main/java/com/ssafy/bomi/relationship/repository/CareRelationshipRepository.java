package com.ssafy.bomi.relationship.repository;

import com.ssafy.bomi.relationship.domain.CareRelationship;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CareRelationshipRepository extends JpaRepository<CareRelationship, UUID> {
}
