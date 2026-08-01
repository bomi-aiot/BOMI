package com.ssafy.bomi.activity.repository;

import com.ssafy.bomi.activity.domain.DailyActivityMetric;
import java.time.LocalDate;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DailyActivityMetricRepository extends JpaRepository<DailyActivityMetric, UUID> {

    /**
     * One senior's aggregated metrics for one local day.
     *
     * <p>{@code metricDate} is the senior's local date, computed with
     * {@code app_user.time_zone}. Passing a UTC date would fetch the wrong day for
     * anything said near midnight.</p>
     *
     * <p>An empty result means no metrics were recorded yet — which is not the same as
     * a day with zeros. The caller must keep that distinction: reporting "did not sleep"
     * for a day we simply did not measure is the kind of false alarm that teaches
     * guardians to stop reading alerts.</p>
     */
    Optional<DailyActivityMetric> findBySeniorIdAndMetricDate(UUID seniorId, LocalDate metricDate);
}
