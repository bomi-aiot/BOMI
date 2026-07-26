package com.ssafy.bomi.relationship;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.domain.RelationshipStatus;
import com.ssafy.bomi.relationship.repository.CareRelationshipRepository;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class CareRelationshipRepositoryTest {

    @Autowired CareRelationshipRepository careRelationshipRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsRolesEnumsAndConnectedAt() {
        CareRelationship rel = CareRelationship.create(
            UUID.randomUUID(), UUID.randomUUID(), RelationshipPriority.PRIMARY);
        CareRelationship saved = careRelationshipRepository.saveAndFlush(rel);
        em.clear();

        CareRelationship found = careRelationshipRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSeniorId()).isNotNull();
        assertThat(found.getGuardianId()).isNotNull();
        assertThat(found.getPriority()).isEqualTo(RelationshipPriority.PRIMARY);
        assertThat(found.getStatus()).isEqualTo(RelationshipStatus.ACTIVE);
        assertThat(found.getConnectedAt()).isNotNull();
    }
}
