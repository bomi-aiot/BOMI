package com.ssafy.bomi.context.application;

import java.util.List;
import org.springframework.stereotype.Component;

/**
 * Stand-in used until the reference document corpus exists (CLAUDE.md §24).
 *
 * <p>Returns nothing and reports unavailable, so a caller asking for documents
 * learns that none could be searched instead of concluding the corpus had no answer.
 * Those two are very different: the first should make the robot ask a clarifying
 * question, the second should make it say it does not know.</p>
 *
 * <p>To replace it, annotate the real implementation {@code @Primary} or delete this
 * class. See {@link NoVectorStoreMemorySearch} for why this is not
 * {@code @ConditionalOnMissingBean}.</p>
 */
@Component
public class NoCorpusDocumentSearch implements DocumentCorpusSearch {

    @Override
    public List<DocumentHit> search(String query, int limit) {
        return List.of();
    }

    @Override
    public boolean isAvailable() {
        return false;
    }
}
