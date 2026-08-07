package com.ssafy.bomi.mqtt.inbound;

/**
 * Idempotency ledger for inbound MQTT messages, keyed by {@code eventId}.
 *
 * <p>MQTT QoS 1 is at-least-once, so the same {@code eventId} may be delivered
 * more than once. This store lets the dispatcher process each {@code eventId}
 * exactly once.</p>
 *
 * <p>Usage contract: call {@link #tryAcquire(String)} before handling; if it
 * returns {@code false} the message is a duplicate and must be skipped. If
 * handling then fails, call {@link #release(String)} so a redelivery can be
 * retried.</p>
 *
 * <p>This is an abstraction on purpose: the MVP uses an in-memory implementation
 * ({@link InMemoryProcessedEventStore}); a persistent (DB "inbox") implementation
 * can replace it later without touching the dispatcher (MVP ERD §12 defers the
 * receive ledger to a future step).</p>
 */
public interface ProcessedEventStore {

    /**
     * Atomically reserves {@code eventId} for processing.
     *
     * @return {@code true} if this is the first time the id is seen (proceed);
     *     {@code false} if it was already reserved/processed (skip as duplicate).
     */
    boolean tryAcquire(String eventId);

    /**
     * Releases a previously acquired {@code eventId} so a later redelivery can be
     * retried. Call this only when handling failed.
     */
    void release(String eventId);
}
