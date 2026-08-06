package com.ssafy.bomi.occupancy.domain;

/**
 * What produced an occupancy change (maps {@code occupancy_event.source}).
 *
 * <p>Recording the source is what makes the ledger interpretable later. A gap in
 * door events means nothing until you know whether the sensor was alive.</p>
 */
public enum OccupancyEventSource {

    /** The entrance node confirmed an actual passage through the door. */
    DOOR_SENSOR,

    /**
     * Speech was detected. Speech beats the sensor: if they are talking, they are
     * home, whatever the door last reported (CLAUDE.md §11).
     */
    SPEECH,

    /**
     * The entrance node's heartbeat stopped, so occupancy was degraded to
     * {@code UNKNOWN}. Without this we could not tell "nobody moved" from "the Pi
     * died" — a silent failure in a safety system.
     */
    HEARTBEAT_TIMEOUT
}
