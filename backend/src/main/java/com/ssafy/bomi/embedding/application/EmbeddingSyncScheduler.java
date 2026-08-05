package com.ssafy.bomi.embedding.application;

import com.ssafy.bomi.embedding.config.EmbeddingProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Runs the embedding sync on a timer, off the turn path (S15P11E102-218).
 *
 * <p><b>The whole bean is conditional.</b> {@code bomi.embedding.sync-enabled} defaults to
 * false, so on a developer machine and in every test this class does not exist. That is
 * about money: the embedding API is metered against a small prepaid balance that also has to
 * cover the prototype demo, and a timer that fires whether or not anyone is watching is the
 * one shape that can drain it unattended.</p>
 *
 * <p><b>Why {@code fixedDelay} and not {@code fixedRate}.</b> {@code fixedRate} schedules the
 * next run from the previous <em>start</em>, so a run that takes longer than the interval
 * queues the next one immediately and they overlap. Two overlapping runs read the same
 * {@code PENDING} rows and pay for both. {@code fixedDelay} measures from the previous
 * finish.</p>
 */
@Component
@ConditionalOnProperty(name = "bomi.embedding.sync-enabled", havingValue = "true")
public class EmbeddingSyncScheduler {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingSyncScheduler.class);

    private final EmbeddingSyncService syncService;
    private final EmbeddingProperties properties;

    public EmbeddingSyncScheduler(EmbeddingSyncService syncService,
        EmbeddingProperties properties) {
        this.syncService = syncService;
        this.properties = properties;
    }

    /**
     * Prepares the sync job once the app is up.
     *
     * <p><b>{@code ensureCollections()} used to be called here too (S15P11E102-218) — it no
     * longer is (S15P11E102-308).</b> This whole bean only exists when sync is switched on, but
     * search can be switched on without sync (that is the recommended demo-day shape), and
     * search needs the collections to exist regardless. Creating them from here would tie two
     * unrelated switches together, so that call moved to
     * {@code VectorStoreStartupInitializer}, which reacts to whether a Qdrant host is
     * configured instead. What stays here — marking stale rows after a model change — only
     * matters when this job actually runs to act on them, so it belongs with the switch that
     * gates the job.</p>
     *
     * <p>{@code ApplicationReadyEvent} rather than {@code @PostConstruct}: a network call
     * during bean construction turns a temporarily unreachable dependency into a failed
     * startup. The service must boot without its derived index.</p>
     *
     * <p>Marking rows stale after a model change costs nothing — no API calls, one UPDATE per
     * table. The re-embedding then happens through the ordinary capped runs.</p>
     */
    @EventListener(ApplicationReadyEvent.class)
    public void prepare() {
        syncService.markStaleAfterModelChange();
        log.info("embedding sync scheduled every {}ms, at most {} billed calls per run",
            properties.getSyncIntervalMillis(), properties.getSyncBatchSize());
    }

    @Scheduled(fixedDelayString = "${bomi.embedding.sync-interval-millis:300000}",
        initialDelayString = "${bomi.embedding.sync-interval-millis:300000}")
    public void run() {
        try {
            syncService.syncDue();
        } catch (Exception error) {
            // 스케줄러에서 예외가 올라가면 그 작업이 조용히 제거된다. 색인 동기화가
            // 멈춘 것은 즉시 드러나지 않고 '로봇이 옛날 얘기를 못 꺼낸다'로만 나타난다.
            log.error("embedding sync run failed; will try again next tick", error);
        }
    }
}
