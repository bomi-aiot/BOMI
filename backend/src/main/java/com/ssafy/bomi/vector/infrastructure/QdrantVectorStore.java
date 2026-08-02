package com.ssafy.bomi.vector.infrastructure;

import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore;
import com.ssafy.bomi.vector.config.QdrantProperties;
import io.qdrant.client.ConditionFactory;
import io.qdrant.client.PointIdFactory;
import io.qdrant.client.QdrantClient;
import io.qdrant.client.QdrantGrpcClient;
import io.qdrant.client.QueryFactory;
import io.qdrant.client.ValueFactory;
import io.qdrant.client.VectorsFactory;
import io.qdrant.client.grpc.Collections.CollectionInfo;
import io.qdrant.client.grpc.Collections.CreateCollection;
import io.qdrant.client.grpc.Collections.Distance;
import io.qdrant.client.grpc.Collections.HnswConfigDiff;
import io.qdrant.client.grpc.Collections.PayloadSchemaType;
import io.qdrant.client.grpc.Collections.VectorParams;
import io.qdrant.client.grpc.Collections.VectorsConfig;
import io.qdrant.client.grpc.Common.Filter;
import io.qdrant.client.grpc.Points.PointStruct;
import io.qdrant.client.grpc.Points.QueryPoints;
import io.qdrant.client.grpc.Points.ScoredPoint;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Qdrant adapter (S15P11E102-218).
 *
 * <p><b>Why the whole class tolerates having no server.</b> A developer laptop without the
 * container, and a production box whose Qdrant is restarting, are both states the service
 * must survive. Semantic ranking disappears; the conversation does not. The alternative —
 * failing the turn — means the senior gets silence because an <em>index</em> is down.</p>
 *
 * <p><b>Every failure is swallowed and logged, and nothing is retried here.</b> Retrying
 * inside the turn spends the budget the senior is waiting on. Writes do not need a retry
 * either: the row keeps {@code embedding_status = PENDING} or {@code FAILED}, and the sync
 * job picks it up later. That bookkeeping is the retry (V5).</p>
 */
@Component
public class QdrantVectorStore implements VectorStore {

    private static final Logger log = LoggerFactory.getLogger(QdrantVectorStore.class);

    /** The one payload key. Named here so the filter and the writer cannot drift apart. */
    private static final String PAYLOAD_SENIOR_ID = "seniorId";

    private final QdrantProperties properties;
    private final Duration timeout;

    /** Null when no host is configured. Every method checks {@link #isAvailable()} first. */
    private QdrantClient client;

    /** Flips to false the first time a call fails, so we stop asking every turn. */
    private volatile boolean reachable;

    public QdrantVectorStore(QdrantProperties properties) {
        this.properties = properties;
        this.timeout = Duration.ofMillis(properties.getTimeoutMillis());
    }

    @PostConstruct
    void connect() {
        if (!properties.isConfigured()) {
            // ★ 조용히 넘어가지 않는다. 의미 검색이 꺼진 채로 도는 것은 정상 동작이지만,
            //   '의도한 것'이어야 한다. 로그가 없으면 몇 주 뒤에 "로봇이 옛날 얘기를 못
            //   꺼낸다"는 증상으로만 발견된다.
            log.warn("no Qdrant host configured: semantic search is OFF. Memory retrieval "
                + "falls back to keyword x importance x recency (S15P11E102-218)");
            return;
        }

        QdrantGrpcClient.Builder builder = QdrantGrpcClient.newBuilder(
            properties.getHost(), properties.getGrpcPort(), properties.isUseTls());
        if (!properties.getApiKey().isBlank()) {
            builder.withApiKey(properties.getApiKey());
        }
        this.client = new QdrantClient(builder.build());
        this.reachable = true;

        log.info("Qdrant connected: {}:{} tls={} dim={}", properties.getHost(),
            properties.getGrpcPort(), properties.isUseTls(), properties.getDimensions());
    }

    @PreDestroy
    void disconnect() {
        if (client != null) {
            client.close();
        }
    }

    @Override
    public boolean isAvailable() {
        return client != null && reachable;
    }

    /**
     * Creates the collections if they are missing; never recreates.
     *
     * <p><b>A dimension mismatch is reported, not repaired.</b> {@code recreateCollection}
     * would fix it in one line and drop every vector doing so. On a config typo that turns
     * a five-character mistake into a full reindex of every memory the household has.</p>
     *
     * <p>The {@code seniorId} payload index is created too. Without it Qdrant filters by
     * scanning the payload of every point, which defeats the point of having an index.</p>
     */
    @Override
    public void ensureCollections() {
        if (!isAvailable()) {
            return;
        }
        for (VectorCollection collection : VectorCollection.values()) {
            try {
                ensureOne(collection);
            } catch (Exception error) {
                log.error("could not prepare Qdrant collection '{}': semantic search will be "
                    + "unavailable for it", collection.collectionName(), error);
            }
        }
    }

    private void ensureOne(VectorCollection collection) throws Exception {
        String name = collection.collectionName();
        if (client.collectionExistsAsync(name, timeout).get()) {
            verifyDimensions(name);
            return;
        }

        client.createCollectionAsync(CreateCollection.newBuilder()
            .setCollectionName(name)
            .setVectorsConfig(VectorsConfig.newBuilder()
                .setParams(VectorParams.newBuilder()
                    .setSize(properties.getDimensions())
                    // 코사인. Upstage 임베딩은 정규화되어 나오므로 코사인과 내적이 같은
                    // 순서를 주지만, 코사인은 0~1 로 떨어져서 점수를 importance·recency 와
                    // 곱하기에 적합하다. 내적은 상한이 없어서 곱셈 가중이 무너진다.
                    .setDistance(Distance.Cosine)
                    // HNSW 를 명시한다. 4096차원에 인덱스를 만들 수 있다는 것이 이 스토어를
                    // 고른 이유이므로, 기본값에 맡기지 않고 파라미터를 적어 둔다.
                    .setHnswConfig(HnswConfigDiff.newBuilder().setM(16).setEfConstruct(128))
                    .build())
                .build())
            .build()).get();

        // seniorId 필터가 인덱스를 타게 한다. 없으면 Qdrant 가 모든 포인트의 payload 를
        // 훑는다 — 한 가구에서는 안 보이지만, 여러 어르신이 한 컬렉션을 쓰는 순간 드러난다.
        client.createPayloadIndexAsync(name, PAYLOAD_SENIOR_ID, PayloadSchemaType.Keyword,
            null, true, null, timeout).get();

        log.info("created Qdrant collection '{}' ({} dims, cosine, HNSW)", name,
            properties.getDimensions());
    }

    private void verifyDimensions(String name) throws Exception {
        CollectionInfo info = client.getCollectionInfoAsync(name, timeout).get();
        long actual = info.getConfig().getParams().getVectorsConfig().getParams().getSize();
        if (actual != properties.getDimensions()) {
            log.error("Qdrant collection '{}' has {} dimensions but the embedding model "
                    + "produces {}. Every upsert will be rejected. Fix bomi.qdrant.dimensions "
                    + "or delete the collection deliberately — this code will not drop it for "
                    + "you, because that would discard every vector in it.",
                name, actual, properties.getDimensions());
        }
    }

    @Override
    public void upsert(VectorCollection collection, UUID id, UUID seniorId, float[] vector) {
        if (!isAvailable()) {
            return;
        }
        if (vector.length != properties.getDimensions()) {
            // 여기서 막지 않으면 gRPC 오류 메시지로만 남고, 원인이 '모델을 바꿨다'라는
            // 사실에서 멀어진다.
            log.error("refusing to upsert a {}-dim vector into '{}' which expects {}: the "
                    + "embedding model and bomi.qdrant.dimensions disagree",
                vector.length, collection.collectionName(), properties.getDimensions());
            return;
        }
        try {
            client.upsertAsync(collection.collectionName(), List.of(PointStruct.newBuilder()
                .setId(PointIdFactory.id(id))
                .setVectors(VectorsFactory.vectors(vector))
                .putPayload(PAYLOAD_SENIOR_ID, ValueFactory.value(seniorId.toString()))
                .build()), timeout).get();
        } catch (Exception error) {
            markUnreachable("upsert into " + collection.collectionName(), error);
        }
    }

    @Override
    public List<VectorHit> search(VectorCollection collection, UUID seniorId,
        float[] queryVector, int limit) {

        if (!isAvailable() || limit <= 0) {
            return List.of();
        }
        try {
            List<ScoredPoint> points = client.queryAsync(QueryPoints.newBuilder()
                .setCollectionName(collection.collectionName())
                .setQuery(QueryFactory.nearest(queryVector))
                .setFilter(Filter.newBuilder()
                    .addMust(ConditionFactory.matchKeyword(
                        PAYLOAD_SENIOR_ID, seniorId.toString()))
                    .build())
                .setLimit(limit)
                // payload 와 vector 를 돌려받지 않는다. 필요한 것은 id 와 점수뿐이고,
                // 내용은 Postgres 에서 다시 읽는다 — 낡은 payload 로 답하는 경로를
                // 아예 만들지 않는다.
                .build(), timeout).get();

            List<VectorHit> hits = new ArrayList<>(points.size());
            for (ScoredPoint point : points) {
                UUID id = parseUuid(point);
                if (id != null) {
                    hits.add(new VectorHit(id, point.getScore()));
                }
            }
            return hits;
        } catch (Exception error) {
            // 검색 실패는 턴을 죽이지 않는다. 얕은 랭킹으로 계속 대답하는 편이,
            // 색인이 죽었다는 이유로 어르신을 침묵 앞에 두는 것보다 낫다.
            markUnreachable("search in " + collection.collectionName(), error);
            return List.of();
        }
    }

    @Override
    public void delete(VectorCollection collection, UUID id) {
        if (!isAvailable()) {
            return;
        }
        try {
            client.deleteAsync(collection.collectionName(),
                List.of(PointIdFactory.id(id)), timeout).get();
        } catch (Exception error) {
            markUnreachable("delete from " + collection.collectionName(), error);
        }
    }

    /**
     * A UUID point id, or null when the point is not one of ours.
     *
     * <p>Qdrant also allows numeric ids. A numeric one here means something else wrote into
     * our collection, and we must not turn it into a memory lookup.</p>
     */
    private UUID parseUuid(ScoredPoint point) {
        String raw = point.getId().getUuid();
        if (raw.isBlank()) {
            log.warn("Qdrant point in a bomi collection has a non-UUID id ({}); ignoring it",
                point.getId().getNum());
            return null;
        }
        try {
            return UUID.fromString(raw);
        } catch (IllegalArgumentException error) {
            log.warn("Qdrant point id '{}' is not a UUID; ignoring it", raw);
            return null;
        }
    }

    /**
     * Marks the store unreachable after a failure.
     *
     * <p>Why latch it off rather than retry per call: a down Qdrant would otherwise cost
     * every turn a full timeout, and the timeout is a large slice of the turn budget. The
     * next restart reconnects; the sync job then reindexes whatever was missed, because the
     * bookkeeping columns never claimed those rows were synced.</p>
     */
    private void markUnreachable(String operation, Exception error) {
        if (reachable) {
            log.error("Qdrant {} failed; semantic search is now OFF until restart. Rows keep "
                + "their embedding_status so the sync job will reindex them.", operation, error);
        }
        reachable = false;
    }
}
