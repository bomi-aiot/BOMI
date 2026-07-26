package com.ssafy.bomi.relationship.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Care relationship linking a senior and a guardian (maps table
 * {@code care_relationship}).
 *
 * <p>Aggregate root. {@code senior_id} and {@code guardian_id} are role-named raw
 * {@link UUID} references to {@code app_user}; the SQL declares no foreign key.</p>
 */
@Entity
@Table(name = "care_relationship")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CareRelationship {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "guardian_id", nullable = false)
    private UUID guardianId;

    @Enumerated(EnumType.STRING)
    @Column(name = "priority", nullable = false, length = 30)
    private RelationshipPriority priority = RelationshipPriority.PRIMARY;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private RelationshipStatus status = RelationshipStatus.ACTIVE;

    @Column(name = "connected_at", nullable = false)
    private OffsetDateTime connectedAt;

    private CareRelationship(UUID seniorId, UUID guardianId, RelationshipPriority priority) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.guardianId = requireNonNull(guardianId, "guardianId");
        this.priority = requireNonNull(priority, "priority");
        this.connectedAt = OffsetDateTime.now();
    }

    public static CareRelationship create(UUID seniorId, UUID guardianId, RelationshipPriority priority) {
        return new CareRelationship(seniorId, guardianId, priority);
    }

    public void changePriority(RelationshipPriority priority) {
        this.priority = requireNonNull(priority, "priority");
    }

    public void changeStatus(RelationshipStatus status) {
        this.status = requireNonNull(status, "status");
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
