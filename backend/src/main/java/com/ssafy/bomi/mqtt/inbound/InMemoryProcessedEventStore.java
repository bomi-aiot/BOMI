package com.ssafy.bomi.mqtt.inbound;

import java.time.Clock;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/**
 * In-memory {@link ProcessedEventStore} keyed by {@code eventId → acquisition time}.
 *
 * <p>Suitable for a single instance / demo. Entries expire after a TTL and the
 * map is size-capped so memory cannot grow unbounded. Not shared across
 * instances and not retained across restarts — see {@link ProcessedEventStore}
 * for the rationale and the future DB-backed swap.</p>
 *
 * <p>Thread-safe: reservation uses atomic {@code putIfAbsent} / compare-and-set,
 * so concurrent duplicates of the same {@code eventId} yield exactly one
 * {@code true}.</p>
 */
@Component
public class InMemoryProcessedEventStore implements ProcessedEventStore {

    private static final Duration DEFAULT_TTL = Duration.ofMinutes(10);
    private static final int DEFAULT_MAX_ENTRIES = 100_000;

    private final ConcurrentMap<String, Long> seen = new ConcurrentHashMap<>();
    private final long ttlMillis;
    private final int maxEntries;
    private final Clock clock;
    private final AtomicLong lastSweepAt = new AtomicLong(0);

    public InMemoryProcessedEventStore() {
        this(DEFAULT_TTL, DEFAULT_MAX_ENTRIES, Clock.systemUTC());
    }

    /** Package-private constructor for tests (custom TTL / capacity / clock). */
    InMemoryProcessedEventStore(Duration ttl, int maxEntries, Clock clock) {
        this.ttlMillis = ttl.toMillis();
        this.maxEntries = maxEntries;
        this.clock = clock;
    }

    @Override
    public boolean tryAcquire(String eventId) {
        requireText(eventId);
        long now = clock.millis();
        sweepIfNeeded(now);

        Long previous = seen.putIfAbsent(eventId, now);
        if (previous == null) {
            return true;
        }
        // A stale (expired) record may not have been swept yet; treat it as new.
        if (now - previous > ttlMillis && seen.replace(eventId, previous, now)) {
            return true;
        }
        return false;
    }

    @Override
    public void release(String eventId) {
        if (eventId != null) {
            seen.remove(eventId);
        }
    }

    /** Expired-entry sweep, throttled by time and triggered early when near capacity. */
    private void sweepIfNeeded(long now) {
        boolean overCapacity = seen.size() >= maxEntries;
        long last = lastSweepAt.get();
        if (!overCapacity && now - last < ttlMillis) {
            return;
        }
        if (!lastSweepAt.compareAndSet(last, now)) {
            return; // another thread is already sweeping
        }
        seen.entrySet().removeIf(entry -> now - entry.getValue() > ttlMillis);
        if (seen.size() > maxEntries) {
            seen.entrySet().stream()
                .sorted(Map.Entry.comparingByValue())
                .limit((long) seen.size() - maxEntries)
                .map(Map.Entry::getKey)
                .toList()
                .forEach(seen::remove);
        }
    }

    private static void requireText(String eventId) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId must not be blank");
        }
    }
}
