package com.ssafy.bomi.mqtt.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class InMemoryProcessedEventStoreTest {

    /** Manually advanced clock for deterministic TTL tests. */
    private static final class TestClock extends Clock {
        private Instant instant;

        TestClock(Instant start) {
            this.instant = start;
        }

        void advance(Duration amount) {
            this.instant = this.instant.plus(amount);
        }

        @Override
        public Instant instant() {
            return instant;
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }
    }

    private InMemoryProcessedEventStore store(TestClock clock) {
        return new InMemoryProcessedEventStore(Duration.ofMinutes(10), 1000, clock);
    }

    @Test
    void firstAcquireSucceedsAndDuplicateIsRejected() {
        InMemoryProcessedEventStore store = store(new TestClock(Instant.parse("2026-07-27T00:00:00Z")));

        assertThat(store.tryAcquire("evt-1")).isTrue();
        assertThat(store.tryAcquire("evt-1")).isFalse();
        assertThat(store.tryAcquire("evt-2")).isTrue();
    }

    @Test
    void releaseAllowsReacquire() {
        InMemoryProcessedEventStore store = store(new TestClock(Instant.parse("2026-07-27T00:00:00Z")));

        assertThat(store.tryAcquire("evt-1")).isTrue();
        store.release("evt-1");
        assertThat(store.tryAcquire("evt-1")).isTrue(); // retriable after release
    }

    @Test
    void reacquiresAfterTtlExpiry() {
        TestClock clock = new TestClock(Instant.parse("2026-07-27T00:00:00Z"));
        InMemoryProcessedEventStore store = store(clock);

        assertThat(store.tryAcquire("evt-1")).isTrue();
        assertThat(store.tryAcquire("evt-1")).isFalse();

        clock.advance(Duration.ofMinutes(11)); // past the 10-minute TTL
        assertThat(store.tryAcquire("evt-1")).isTrue();
    }

    @Test
    void rejectsBlankEventId() {
        InMemoryProcessedEventStore store = store(new TestClock(Instant.parse("2026-07-27T00:00:00Z")));
        assertThatThrownBy(() -> store.tryAcquire("  ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> store.tryAcquire(null)).isInstanceOf(IllegalArgumentException.class);
    }
}
