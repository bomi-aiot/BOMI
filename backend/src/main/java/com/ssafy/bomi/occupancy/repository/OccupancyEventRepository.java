package com.ssafy.bomi.occupancy.repository;

import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import com.ssafy.bomi.occupancy.domain.OccupancyEvent;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OccupancyEventRepository extends JpaRepository<OccupancyEvent, UUID> {

    /**
     * How many passages of one direction happened in a window.
     *
     * <p>The daily aggregation counts {@code OUT} to get the day's outing count. Outings
     * are the second activity signal after speech volume, and a sharp drop reads as
     * depression or declining health (CLAUDE.md §11).</p>
     *
     * <p>Counted rather than loaded: the guardian sees an aggregate, never the movement
     * log itself. A daily "left 14:03, returned 15:20" feed is surveillance; "she was out
     * unusually long today" is care. Keeping the raw rows out of the service makes the
     * wrong thing harder to build by accident.</p>
     *
     * <p>Half-open window ({@code >= from, < to}) so consecutive days never double-count
     * a passage that happened exactly at midnight.</p>
     */
    long countBySeniorIdAndDirectionAndOccurredAtGreaterThanEqualAndOccurredAtLessThan(
        UUID seniorId, OccupancyDirection direction, OffsetDateTime from, OffsetDateTime to);
}
