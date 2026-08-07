package com.ssafy.bomi.occupancy.domain;

/**
 * Direction of a confirmed passage through the entrance
 * (maps {@code occupancy_event.direction}).
 *
 * <p>Null on events that changed occupancy without anyone passing the door — a
 * heartbeat timeout or a speech-derived promotion. The sensor knows direction, not
 * identity, so a visitor entering looks exactly like the senior returning; that
 * ambiguity is resolved by speech, never by this value alone (CLAUDE.md §11).</p>
 */
public enum OccupancyDirection {
    IN,
    OUT
}
