package com.ssafy.bomi.context.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.context.config.DocumentCorpusProperties;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.DefaultResourceLoader;

class ClasspathDocumentCorpusSearchTest {

    @Test
    @DisplayName("복지제도 질문은 버전과 인용이 있는 실제 코퍼스 청크를 반환한다")
    void welfareQuestionReturnsTraceableChunks() {
        ClasspathDocumentCorpusSearch search = loadedSearch(true);

        DocumentCorpusSearch.SearchResult result = search.search("복지제도 알려줘", 3);

        assertThat(search.isAvailable()).isTrue();
        assertThat(result.used()).isTrue();
        assertThat(result.fallbackReason()).isNull();
        assertThat(result.hits()).hasSize(3)
            .allSatisfy(hit -> {
                assertThat(hit.source()).isEqualTo("복지로");
                assertThat(hit.version()).isNotBlank();
                assertThat(hit.chunkId()).startsWith("bokjiro-");
                assertThat(hit.citation()).isNotBlank();
                assertThat(hit.url()).startsWith("https://www.bokjiro.go.kr/");
            });
    }

    @Test
    @DisplayName("코퍼스를 조회한 0건과 코퍼스 미가용을 구분한다")
    void zeroHitsAndUnavailableCorpusAreDifferent() {
        DocumentCorpusSearch.SearchResult noHits = loadedSearch(true)
            .search("양자역학 실험 장비", 3);
        DocumentCorpusSearch.SearchResult unavailable = loadedSearch(false)
            .search("복지제도", 3);

        assertThat(noHits.used()).isTrue();
        assertThat(noHits.hits()).isEmpty();
        assertThat(noHits.fallbackReason()).isEqualTo("document_no_hits");
        assertThat(unavailable.used()).isFalse();
        assertThat(unavailable.fallbackReason()).isEqualTo("document_corpus_unavailable");
    }

    private ClasspathDocumentCorpusSearch loadedSearch(boolean enabled) {
        DocumentCorpusProperties properties = new DocumentCorpusProperties();
        properties.setEnabled(enabled);
        ClasspathDocumentCorpusSearch search = new ClasspathDocumentCorpusSearch(
            new ObjectMapper(), new DefaultResourceLoader(), properties);
        search.load();
        return search;
    }
}
