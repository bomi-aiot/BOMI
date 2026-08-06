package com.ssafy.bomi.occupancy.application;

import com.ssafy.bomi.occupancy.config.EntranceProperties;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Works out whether somebody came in or went out (S15P11E102-226).
 *
 * <p><b>Neither sensor knows direction.</b> The contact sensor says the door opened; the
 * PIR says something moved in the hallway. Direction only exists in the <em>order</em> of
 * the two:</p>
 *
 * <pre>
 *   door opened  →  inside motion   =  IN   (they came home)
 *   inside motion →  door opened    =  OUT  (they left)
 *   only one of the two             =  UNKNOWN (door opened, nobody passed)
 * </pre>
 *
 * <p><b>Why this lives on the server.</b> The correlation window is an empirical value —
 * it depends on hallway length and how fast this particular senior walks. On the robot it
 * would need a firmware or robot deploy to tune; here it is a config change
 * (CLAUDE.md §11, §24).</p>
 *
 * <p><b>Why the buffer is in memory.</b> These are seconds-scale sensor pairs. Persisting
 * them would write rows nobody ever reads again, and a restart mid-passage costs one
 * greeting — not a safety signal. The resolved passage <em>is</em> persisted, as an
 * {@code occupancy_event}.</p>
 *
 * <p>Thread-safe: MQTT inbound and the robot's HTTP forward can both land here.</p>
 */
@Component
public class EntranceDirectionResolver {

    private static final Logger log = LoggerFactory.getLogger(EntranceDirectionResolver.class);

    /** What the entrance sensors can report. */
    public enum Signal {
        /** SNZB-04P contact opened. */
        DOOR_OPENED,
        /** SNZB-03P detected movement in the hallway. */
        MOTION
    }

    private final EntranceProperties properties;
    private final Map<UUID, Deque<Observation>> recent = new ConcurrentHashMap<>();

    public EntranceDirectionResolver(EntranceProperties properties) {
        this.properties = properties;
    }

    /**
     * Records one signal and returns a passage if this completes one.
     *
     * @param at when the signal was observed. The Jetson's normalized clock, never the
     *     Raspberry Pi's — a Pi without a battery-backed RTC can boot years off, and a
     *     wrong ordering here inverts the direction (CLAUDE.md §11)
     * @return the direction if the pair completes a passage, otherwise empty
     */
    public Optional<OccupancyDirection> observe(UUID seniorId, Signal signal, OffsetDateTime at) {
        Deque<Observation> history = recent.computeIfAbsent(seniorId, key -> new ArrayDeque<>());

        synchronized (history) {
            prune(history, at);

            Observation partner = findPartner(history, signal, at);
            history.addLast(new Observation(signal, at));

            if (partner == null) {
                // Half a passage. Wait for the other sensor; if it never comes, the pruning
                // above drops this one and no direction is ever claimed. A door that opened
                // with nobody passing through must not move occupancy.
                return Optional.empty();
            }

            // The pair is consumed so a third signal cannot reuse it. Without this, a
            // door-motion-motion burst would resolve twice and the senior would be greeted
            // as arriving, then as arriving again.
            history.clear();

            OccupancyDirection direction = partner.signal() == Signal.DOOR_OPENED
                ? OccupancyDirection.IN
                : OccupancyDirection.OUT;
            log.info("entrance passage resolved as {} for senior {} ({} then {})",
                direction, seniorId, partner.signal(), signal);
            return Optional.of(direction);
        }
    }

    /**
     * Forgets everything buffered for a senior.
     *
     * <p>Used when something else settled the question — speech proving the senior is home,
     * for instance. Leaving a stale half-passage would let an unrelated signal minutes later
     * pair with it and invent a direction.</p>
     */
    public void forget(UUID seniorId) {
        Deque<Observation> history = recent.get(seniorId);
        if (history == null) {
            return;
        }
        synchronized (history) {
            history.clear();
        }
    }

    /**
     * The most recent observation of the <em>other</em> sensor, if it is still in window.
     *
     * <p>Two signals from the same sensor never form a passage. Two door-opens in a row is
     * somebody opening the door twice, not a direction.</p>
     */
    private Observation findPartner(Deque<Observation> history, Signal signal, OffsetDateTime at) {
        Duration window = properties.getCorrelationWindow();
        for (Observation candidate : history) {
            if (candidate.signal() == signal) {
                continue;
            }
            if (!candidate.at().plus(window).isBefore(at)) {
                return candidate;
            }
        }
        return null;
    }

    /** Drops observations too old to pair with anything. */
    private void prune(Deque<Observation> history, OffsetDateTime now) {
        Duration window = properties.getCorrelationWindow();
        history.removeIf(observation -> observation.at().plus(window).isBefore(now));
    }

    private record Observation(Signal signal, OffsetDateTime at) {
    }
}
