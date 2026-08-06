package com.ssafy.bomi.context.application;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.context.config.DocumentCorpusProperties;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.InputStream;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;

/**
 * Searches a small, versioned welfare-information corpus bundled with the backend.
 *
 * <p>This MVP deliberately has no network or embedding call on the turn path. Character
 * bigrams tolerate common Korean particles and spacing differences better than exact tokens,
 * while the source metadata makes every prompt chunk auditable. Memory and summary semantic
 * search still use Qdrant; public-document ranking can move there later only after a measured
 * quality gain justifies another paid embedding/index lifecycle.</p>
 */
@Component
@Primary
public class ClasspathDocumentCorpusSearch implements DocumentCorpusSearch {

    private static final Logger log = LoggerFactory.getLogger(ClasspathDocumentCorpusSearch.class);
    private static final double MIN_SCORE = 0.12;

    private final ObjectMapper objectMapper;
    private final ResourceLoader resourceLoader;
    private final DocumentCorpusProperties properties;

    private List<CorpusChunk> chunks = List.of();
    private String corpusVersion;

    public ClasspathDocumentCorpusSearch(ObjectMapper objectMapper,
        ResourceLoader resourceLoader, DocumentCorpusProperties properties) {
        this.objectMapper = objectMapper;
        this.resourceLoader = resourceLoader;
        this.properties = properties;
    }

    @PostConstruct
    void load() {
        if (!properties.isEnabled()) {
            log.warn("document corpus OFF (bomi.document-corpus.enabled=false)");
            return;
        }
        Resource resource = resourceLoader.getResource(properties.getResource());
        try (InputStream input = resource.getInputStream()) {
            CorpusFile corpus = objectMapper.readValue(input, CorpusFile.class);
            if (corpus.corpusVersion() == null || corpus.corpusVersion().isBlank()
                || corpus.chunks() == null || corpus.chunks().isEmpty()) {
                log.error("document corpus '{}' has no version or chunks; document RAG is OFF",
                    properties.getResource());
                return;
            }
            this.corpusVersion = corpus.corpusVersion();
            this.chunks = List.copyOf(corpus.chunks());
            log.info("document corpus loaded: version={} chunks={} resource={}",
                corpusVersion, chunks.size(), properties.getResource());
        } catch (IOException | RuntimeException error) {
            log.error("could not load document corpus '{}'; document RAG is OFF",
                properties.getResource(), error);
            this.chunks = List.of();
        }
    }

    @Override
    public boolean isAvailable() {
        return properties.isEnabled() && !chunks.isEmpty();
    }

    @Override
    public SearchResult search(String query, int limit) {
        long startedAt = System.nanoTime();
        if (!isAvailable()) {
            return result(List.of(), false, "document_corpus_unavailable", startedAt);
        }
        if (query == null || query.isBlank()) {
            return result(List.of(), false, "query_blank", startedAt);
        }
        if (limit <= 0) {
            return result(List.of(), false, "no_document_budget", startedAt);
        }

        List<ScoredChunk> ranked = new ArrayList<>();
        for (CorpusChunk chunk : chunks) {
            double score = score(query, chunk);
            if (score >= MIN_SCORE) {
                ranked.add(new ScoredChunk(chunk, score));
            }
        }
        List<DocumentHit> hits = ranked.stream()
            .sorted(Comparator.comparingDouble(ScoredChunk::score).reversed()
                .thenComparing(scored -> scored.chunk().chunkId()))
            .limit(limit)
            .map(scored -> toHit(scored.chunk()))
            .toList();
        return result(hits, true, hits.isEmpty() ? "document_no_hits" : null, startedAt);
    }

    private DocumentHit toHit(CorpusChunk chunk) {
        String version = chunk.version() == null || chunk.version().isBlank()
            ? corpusVersion : chunk.version();
        return new DocumentHit(
            chunk.title(), chunk.content(), chunk.source(), version, chunk.chunkId(),
            chunk.citation(), chunk.url());
    }

    private double score(String query, CorpusChunk chunk) {
        Set<String> queryBigrams = bigrams(normalize(query));
        if (queryBigrams.isEmpty()) {
            return 0.0;
        }
        String keyText = chunk.title() + " " + String.join(" ", chunk.keywords());
        String fullText = keyText + " " + chunk.content();
        double keyOverlap = overlap(queryBigrams, bigrams(normalize(keyText)));
        double fullOverlap = overlap(queryBigrams, bigrams(normalize(fullText)));

        String normalizedQuery = normalize(query);
        boolean exactKeyword = chunk.keywords().stream()
            .map(this::normalize)
            .anyMatch(keyword -> !keyword.isBlank()
                && (normalizedQuery.contains(keyword) || keyword.contains(normalizedQuery)));
        return keyOverlap * 0.7 + fullOverlap * 0.3 + (exactKeyword ? 1.0 : 0.0);
    }

    private double overlap(Set<String> query, Set<String> candidate) {
        long matches = query.stream().filter(candidate::contains).count();
        return query.isEmpty() ? 0.0 : (double) matches / query.size();
    }

    private Set<String> bigrams(String text) {
        if (text.length() < 2) {
            return Set.of();
        }
        Set<String> grams = new HashSet<>();
        for (int index = 0; index < text.length() - 1; index++) {
            grams.add(text.substring(index, index + 2));
        }
        return grams;
    }

    private String normalize(String value) {
        if (value == null) {
            return "";
        }
        String unicode = Normalizer.normalize(value, Normalizer.Form.NFKC)
            .toLowerCase(Locale.ROOT);
        return unicode.replaceAll("[^\\p{L}\\p{N}]", "");
    }

    private SearchResult result(List<DocumentHit> hits, boolean used, String fallbackReason,
        long startedAt) {
        long latencyMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedAt);
        return new SearchResult(hits, used, fallbackReason, latencyMs);
    }

    private record CorpusFile(String corpusVersion, List<CorpusChunk> chunks) {}

    private record CorpusChunk(
        String chunkId,
        String title,
        String content,
        String source,
        String version,
        String citation,
        String url,
        List<String> keywords
    ) {
        private CorpusChunk {
            keywords = keywords == null ? List.of() : List.copyOf(keywords);
        }
    }

    private record ScoredChunk(CorpusChunk chunk, double score) {}
}
