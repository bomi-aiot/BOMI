package com.ssafy.bomi.embedding.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.abort;

import com.ssafy.bomi.embedding.config.EmbeddingProperties;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

/**
 * The one test that spends money (S15P11E102-218).
 *
 * <pre>UPSTAGE_API_KEY=... ./gradlew billedTest</pre>
 *
 * <p><b>Three billed calls, in one test method.</b> The project runs on a small prepaid
 * balance that also has to cover the prototype demo, so this file is written around a budget
 * rather than around coverage. Three calls is the minimum that can answer the only question a
 * fake cannot: <em>do the passage model and the query model actually share a vector
 * space?</em> — one query and two passages, so the answer can be a comparison.</p>
 *
 * <p><b>Why not two calls and a threshold.</b> That was the first version, and it failed: the
 * measured cosine between a query and its matching passage was <b>0.451</b>. Not because
 * anything was broken — an asymmetric passage/query pair simply does not produce
 * near-1.0 cosines, and "greater than 0.5" was a number invented rather than measured. A
 * threshold like that tests the guess, and the honest fix is not to raise or lower it but to
 * stop asserting an absolute value at all. What the models promise is <em>ranking</em>, so
 * that is what gets asserted.</p>
 *
 * <p>Everything else about embedding is covered for free elsewhere — which model is asked for
 * ({@code QdrantMemorySearchTest}), the spending cap and the bookkeeping
 * ({@code EmbeddingSyncServiceTest}), the store round trip
 * ({@code QdrantVectorStoreIntegrationTest}). None of those needed a real model, so none of
 * them cost anything. Adding cases here would each cost a call, and would not tell us more.</p>
 *
 * <p><b>Why the question needs a real call at all.</b> If the two models were unpaired — a
 * wrong model name, a version bump that split them — nothing would fail. Search would return
 * slightly worse neighbours forever and no assertion anywhere would notice. That is the one
 * failure mode a fake cannot reproduce, because the fake defines its own vector space.</p>
 *
 * <p>{@code @TestInstance(PER_CLASS)} so the client is built once. Without a key the test
 * <b>aborts loudly</b> rather than passing — a skipped test reporting green is how an
 * unverified claim gets into a merge request.</p>
 */
@Tag("billed")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@DisplayName("★ 과금됨: Upstage passage/query 왕복 (호출 3회)")
class UpstageEmbeddingBilledTest {

    private static UpstageEmbeddingClient client;
    private static EmbeddingProperties properties;

    @BeforeAll
    static void buildClient() {
        String apiKey = System.getProperty("bomi.test.upstage.apiKey", "");
        if (apiKey.isBlank()) {
            abort("UPSTAGE_API_KEY 가 없습니다. 이 테스트는 실제로 과금되는 API 를 "
                + "호출합니다 (UPSTAGE_API_KEY=... ./gradlew billedTest). "
                + "건너뛴 것을 통과로 읽지 마십시오.");
        }

        properties = new EmbeddingProperties();
        properties.setEnabled(true);
        properties.setApiKey(apiKey);
        // 실제 왕복은 턴 예산용 1.2초보다 오래 걸릴 수 있다. 여기서 타임아웃으로 실패하면
        // 호출은 이미 과금된 뒤다 — 돈을 쓰고 답을 못 받는 최악의 조합이다.
        properties.setTimeoutMillis(20_000);

        client = new UpstageEmbeddingClient(properties);
    }

    @Test
    @DisplayName("★★ query 가 관련 passage 를 무관한 passage 보다 앞에 놓는다 (과금 3회)")
    void thequeryModelRanksTheRelatedPassageHigher() {
        /*
         * ★★★ 이 왕복이 확인하는 단 하나의 사실: 두 모델이 같은 벡터 공간을 쓰는가.
         *
         * 짝으로 학습된 모델이면 검색 문장은 관련 있는 저장 문장에 더 가깝다. 짝이
         * 아니면(모델 이름이 어긋났거나 버전이 갈라졌으면) 순서가 사실상 무작위가 된다.
         * 그런데 예외는 나지 않는다 — 검색이 영원히 조금 더 나쁜 이웃을 돌려줄 뿐이고,
         * 시스템 안에 그것을 알려주는 장치가 없다. 그래서 실제 호출이 필요하다.
         *
         * 절대값을 걸지 않는다. 실측 0.451(관련 쌍)이 말해 주듯 비대칭 쌍의 코사인은
         * 1 근처로 가지 않는다. 모델이 약속하는 것은 '순서'이므로 순서를 검증한다.
         */
        float[] relatedPassage = client.embedPassage("어르신은 무릎이 아프다고 자주 말씀하신다.");
        float[] unrelatedPassage = client.embedPassage("어르신은 낚시를 좋아하신다.");
        float[] query = client.embedQuery("무릎이 아파요");

        assertThat(client.billedCallCount())
            .as("이 테스트는 정확히 3회만 호출해야 한다. 늘어났다면 예산 설계가 깨진 것이다")
            .isEqualTo(3);

        assertThat(relatedPassage.length)
            .as("설정된 차원과 실제 모델 출력이 같아야 한다. 다르면 Qdrant 컬렉션이 "
                + "모든 업서트를 거부한다")
            .isEqualTo(properties.getDimensions())
            .isEqualTo(4096);
        assertThat(query.length).isEqualTo(relatedPassage.length);
        assertThat(unrelatedPassage.length).isEqualTo(relatedPassage.length);

        double related = cosine(query, relatedPassage);
        double unrelated = cosine(query, unrelatedPassage);

        assertThat(related)
            .as("무릎 질의가 무릎 문장에 더 가까워야 한다. 뒤집히면 두 모델이 짝이 "
                + "아니다 (관련=%s, 무관=%s)", related, unrelated)
            .isGreaterThan(unrelated);

        // 완전히 어긋난 공간(직교)인지만 아주 느슨하게 본다. 이 값 자체에는 의미가 없고,
        // 0 에 붙어 있으면 두 모델이 서로 다른 공간에 있다는 신호다.
        assertThat(related)
            .as("관련 쌍이 직교에 가깝다면 같은 벡터 공간이 아니다 (실측=%s)", related)
            .isGreaterThan(0.1);
    }

    /**
     * Cosine similarity.
     *
     * <p>Computed here rather than trusting normalization: if the model ever stops returning
     * unit vectors, a dot product would silently start meaning something else, and the
     * threshold above would stop testing what it claims to test.</p>
     */
    private static double cosine(float[] a, float[] b) {
        double dot = 0;
        double normA = 0;
        double normB = 0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
            normA += (double) a[i] * a[i];
            normB += (double) b[i] * b[i];
        }
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }
}
