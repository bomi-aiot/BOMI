package com.ssafy.bomi.embedding.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Turns Spring scheduling on, and only for the embedding sync (S15P11E102-218).
 *
 * <p><b>Why this class exists at all.</b> Nothing in this application had
 * {@code @EnableScheduling} before. Without it {@code @Scheduled} is inert — the annotation
 * is read by nobody, the method never runs, and there is no warning. The sync job would have
 * looked correct in review and simply never fired.</p>
 *
 * <p><b>Why it is conditional rather than on the main application class.</b> Putting it there
 * would enable scheduling for the whole app forever, so the next {@code @Scheduled} anyone
 * writes starts running the moment it is merged, in every environment including tests. Here,
 * the scheduler thread only exists when someone deliberately switched the sync on — which
 * matters because the job it drives spends money on a metered API.</p>
 */
@Configuration
@ConditionalOnProperty(name = "bomi.embedding.sync-enabled", havingValue = "true")
@EnableScheduling
public class EmbeddingSchedulingConfig {
}
