package com.ssafy.bomi.embedding.config;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

/**
 * The passage/query model pairing guard (S15P11E102-308).
 *
 * <p>Mixing the two models does not throw anywhere in the call chain — {@code EmbeddingClient}'s
 * Javadoc says so explicitly. An error log at startup is the only signal this misconfiguration
 * ever produces, so the log line itself is the thing under test, not a return value or an
 * exception. That is why this attaches a Logback {@link ListAppender} directly to the logger
 * rather than asserting on a thrown exception.</p>
 */
class EmbeddingPropertiesTest {

    private Logger logger;
    private ListAppender<ILoggingEvent> appender;

    @BeforeEach
    void attachAppender() {
        logger = (Logger) LoggerFactory.getLogger(EmbeddingProperties.class);
        appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void detachAppender() {
        logger.detachAppender(appender);
    }

    @Test
    @DisplayName("★ passage 모델과 query 모델이 같으면 기동 시 error 로그가 1줄 남는다")
    void logsAnErrorWhenBothModelsAreTheSame() {
        EmbeddingProperties properties = new EmbeddingProperties();
        properties.setPassageModel("embedding-query");
        properties.setQueryModel("embedding-query");

        // 실제로는 @PostConstruct 가 Spring 컨테이너에 의해 불린다. 여기서는 컨테이너를
        // 띄우지 않고 같은 메서드를 직접 호출한다 — 검증하려는 것은 로직이지 배선이 아니다.
        properties.validateModelPairing();

        assertThat(appender.list)
            .filteredOn(event -> event.getLevel() == Level.ERROR)
            .as("모델이 같으면 error 로그가 정확히 한 줄이어야 한다")
            .hasSize(1);
    }

    @Test
    @DisplayName("모델이 다르면(정상 배선) 조용하다")
    void staysQuietWhenTheModelsArePaired() {
        EmbeddingProperties properties = new EmbeddingProperties();
        // 기본값을 그대로 둔다: passage-model="embedding-passage", query-model="embedding-query".

        properties.validateModelPairing();

        assertThat(appender.list).isEmpty();
    }
}
