package com.ssafy.bomi.scenario.repository;

import com.ssafy.bomi.scenario.domain.WalkRequestIngress;
import com.ssafy.bomi.scenario.domain.WalkRequestReceipt;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface WalkRequestReceiptRepository
    extends JpaRepository<WalkRequestReceipt, UUID> {

    Optional<WalkRequestReceipt> findByIngressAndRequestId(
        WalkRequestIngress ingress, String requestId);

    /**
     * Atomically claims a durable idempotency key without aborting the transaction when another
     * Backend instance already owns it. The subsequent lookup observes the winner's committed
     * decision because PostgreSQL waits for the conflicting transaction before returning zero.
     */
    @Modifying(flushAutomatically = true)
    @Query(value = """
        INSERT INTO walk_request_receipt (
            id, ingress, request_id, robot_device_id, action, source,
            conversation_id, occurred_at, disposition, created_at
        ) VALUES (
            :id, :ingress, :requestId, :robotDeviceId, :action, :source,
            :conversationId, :occurredAt, 'RECEIVED', CURRENT_TIMESTAMP
        ) ON CONFLICT DO NOTHING
        """, nativeQuery = true)
    int insertIfAbsent(
        @Param("id") UUID id,
        @Param("ingress") String ingress,
        @Param("requestId") String requestId,
        @Param("robotDeviceId") String robotDeviceId,
        @Param("action") String action,
        @Param("source") String source,
        @Param("conversationId") UUID conversationId,
        @Param("occurredAt") OffsetDateTime occurredAt);
}
