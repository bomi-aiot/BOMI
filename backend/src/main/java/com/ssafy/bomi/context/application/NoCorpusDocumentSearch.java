package com.ssafy.bomi.context.application;

import org.springframework.stereotype.Component;

/**
 * Explicit fallback used when the bundled reference document corpus is disabled or fails.
 *
 * <p>Returns nothing and reports unavailable, so a caller asking for documents
 * learns that none could be searched instead of concluding the corpus had no answer.
 * Those two are very different: the first should make the robot ask a clarifying
 * question, the second should make it say it does not know.</p>
 *
 * <p>{@link ClasspathDocumentCorpusSearch} is {@code @Primary}; this bean remains as the
 * documented no-corpus contract and a safe implementation for isolated wiring.</p>
 */
@Component
public class NoCorpusDocumentSearch implements DocumentCorpusSearch {

    @Override
    public SearchResult search(String query, int limit) {
        return new SearchResult(java.util.List.of(), false, "document_corpus_unavailable", 0);
    }

    @Override
    public boolean isAvailable() {
        return false;
    }
}
