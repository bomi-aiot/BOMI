package com.ssafy.bomi.infra;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.Yaml;

/**
 * {@code application.yml} 이 읽는 환경변수를 compose 가 실제로 넘겨주는지 확인한다.
 *
 * <p><b>왜 이 테스트가 생겼나.</b> S15P11E102-218 에서 실제로 빠뜨렸다.
 * {@code application.yml} 은 {@code ${EMBEDDING_ENABLED:false}} 를 읽는데
 * {@code compose.prod.yml} 의 backend 서비스가 그 변수를 넘기지 않았다.</p>
 *
 * <p>Docker 는 호스트 환경변수를 컨테이너로 흘려보내지 않는다. {@code environment:} 에
 * 명시하지 않은 변수는 컨테이너 안에 <b>존재하지 않는다.</b> 그래서
 * {@code production.env} 에 {@code EMBEDDING_ENABLED=true} 를 적어도 아무 일도 일어나지
 * 않고, Spring 은 기본값 {@code false} 를 그대로 읽는다.</p>
 *
 * <p><b>이 실패가 위험한 이유:</b> 아무것도 깨지지 않는다. 예외도, 경고도 없다. 운영자는
 * env 파일을 고쳤고, 배포는 성공했고, 기능은 꺼져 있다. 유일한 단서는 기동 로그의
 * "embedding OFF" 한 줄이며, 그것을 찾으려면 이미 무언가 이상하다는 것을 알고 있어야
 * 한다.</p>
 *
 * <p>같은 모양의 실패가 다시 나지 않게 두 파일을 대조한다. 새 {@code ${VAR}} 을 넣는
 * 사람은 compose 에도 넣거나, 넣지 않는 이유를 아래 목록에 적어야 한다.</p>
 */
@DisplayName("compose 가 application.yml 의 환경변수를 실제로 넘기는가")
class ComposeEnvironmentPassthroughTest {

    /** {@code ${NAME}}, {@code ${NAME:default}}, {@code ${NAME:?msg}} 를 모두 잡는다. */
    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{([A-Z_][A-Z0-9_]*)");

    /**
     * 일부러 넘기지 않는 변수들. <b>각 줄에 이유가 있어야 한다.</b>
     *
     * <p>판단 기준은 하나다 — <b>운영 중에 값을 바꿔서 동작을 바꿀 일이 있는가.</b>
     * 있으면 넘긴다. 없으면(바꾸려면 재배포나 데이터 재구축이 필요하면) 넘기지 않는다.
     * 넘기지 않는 변수를 env 파일에 적어 두면, 적은 사람은 그것이 먹는다고 믿는다.</p>
     */
    private static final Map<String, String> INTENTIONALLY_NOT_FORWARDED = Map.of(
        "MQTT_BROKER_HOST",
        "MQTT_BROKER_URL 의 기본값을 조립하는 데만 쓰인다. compose 는 완성된 URL 을 직접 넘긴다",
        "MQTT_BROKER_PORT",
        "MQTT_BROKER_HOST 와 함께 기본 URL 을 만드는 조각이다. URL 을 넘기므로 도달할 필요가 없다",
        "QDRANT_DIMENSIONS",
        "차원을 바꾸면 컬렉션을 다시 만들어야 하고 전량 재색인이다. env 를 고쳐서 되는 일이 아니다",
        "EMBEDDING_DIMENSIONS",
        "모델의 출력 차원이므로 코드 상수에 가깝다. 바꾸려면 컬렉션부터 다시 만들어야 한다",
        "UPSTAGE_PASSAGE_MODEL",
        "모델을 바꾸면 기존 벡터 전체가 무효다(벡터 공간이 다르다). 의도된 재배포 작업이다",
        "UPSTAGE_QUERY_MODEL",
        "passage 모델과 짝을 유지해야 한다. 한쪽만 바꿀 수 있으면 검색이 조용히 나빠진다",
        "UPSTAGE_BASE_URL",
        "API 엔드포인트가 바뀌는 것은 배포 사건이고, 운영 중 전환할 대상이 아니다",
        "QDRANT_TIMEOUT_MILLIS",
        "턴 지연 예산(약 2초)에서 나온 값이다. 늘리는 것은 예산을 다시 정하는 판단이다",
        "EMBEDDING_TIMEOUT_MILLIS",
        "질의 임베딩이 턴 예산 안에 있다. 이 값을 늘리면 어르신이 더 오래 침묵을 듣는다",
        "EMBEDDING_SYNC_INTERVAL_MILLIS",
        "배치 간격이다. 급하면 sync-enabled 를 끄면 되므로 간격만 따로 조정할 이유가 없다");

    @Test
    @DisplayName("★ application.yml 이 읽는 변수는 compose 가 넘기거나, 안 넘기는 이유가 있어야 한다")
    void everyPlaceholderIsForwardedOrJustified() throws IOException {
        Set<String> placeholders = placeholdersIn(applicationYml());
        Set<String> forwarded = backendEnvironmentKeys();

        Set<String> unexplained = new TreeSet<>(placeholders);
        unexplained.removeAll(forwarded);
        unexplained.removeAll(INTENTIONALLY_NOT_FORWARDED.keySet());

        assertThat(unexplained)
            .as("""
                application.yml 이 읽지만 compose 가 넘기지 않는 변수다. \
                production.env 에 적어도 컨테이너에 도달하지 않고, Spring 은 기본값을 \
                그대로 읽는다. 아무것도 깨지지 않으므로 아무도 알아채지 못한다. \
                compose.prod.yml 의 backend environment 에 추가하거나, 넘기지 않는 \
                이유를 INTENTIONALLY_NOT_FORWARDED 에 적는다: %s""", unexplained)
            .isEmpty();
    }

    @Test
    @DisplayName("★ 의미 검색 스위치가 컨테이너에 도달한다 — 218 에서 빠뜨린 것")
    void theSemanticSearchSwitchesActuallyReachTheContainer() throws IOException {
        Set<String> forwarded = backendEnvironmentKeys();

        assertThat(forwarded)
            .as("이 셋이 없으면 UPSTAGE_API_KEY 를 넣어도 의미 검색이 켜지지 않는다")
            .contains("EMBEDDING_ENABLED", "EMBEDDING_SYNC_ENABLED", "UPSTAGE_API_KEY");
    }

    @Test
    @DisplayName("과금 상한을 재배포 없이 줄일 수 있다")
    void theSpendingCapIsTunableWithoutARedeploy() throws IOException {
        assertThat(backendEnvironmentKeys())
            .as("임베딩 API 는 과금되고 잔액이 작다. 상한을 줄이려고 재배포해야 하면 늦는다")
            .contains("EMBEDDING_SYNC_BATCH_SIZE");
    }

    @Test
    @DisplayName("안 넘기기로 한 변수에는 이유가 적혀 있다")
    void everyExclusionCarriesAReason() {
        INTENTIONALLY_NOT_FORWARDED.forEach((name, reason) ->
            assertThat(reason.length())
                .as("%s 를 넘기지 않는 이유가 너무 짧다. 다음 사람이 판단을 이어받을 수 "
                    + "있게 적는다", name)
                .isGreaterThan(20));
    }

    @Test
    @DisplayName("이유 목록에 이미 넘기는 변수가 남아 있지 않다")
    void theExclusionListDoesNotContradictTheComposeFile() throws IOException {
        Set<String> forwarded = backendEnvironmentKeys();

        Set<String> contradictions = new TreeSet<>(INTENTIONALLY_NOT_FORWARDED.keySet());
        contradictions.retainAll(forwarded);

        assertThat(contradictions)
            .as("compose 가 넘기고 있는데 '안 넘긴다'고 적혀 있다. 둘 중 하나가 낡았고, "
                + "이 상태에서는 목록을 읽는 사람이 잘못된 판단을 한다: %s", contradictions)
            .isEmpty();
    }

    // ── 파일 읽기 ────────────────────────────────────────────────────────────

    private static Set<String> placeholdersIn(String text) {
        Set<String> names = new LinkedHashSet<>();
        Matcher matcher = PLACEHOLDER.matcher(text);
        while (matcher.find()) {
            names.add(matcher.group(1));
        }
        return names;
    }

    private static String applicationYml() throws IOException {
        return Files.readString(
            Path.of("src", "main", "resources", "application.yml"), StandardCharsets.UTF_8);
    }

    /**
     * compose 의 backend 서비스가 컨테이너에 넣어 주는 변수 이름들.
     *
     * <p>compose 파일을 위로 찾아 올라간다. Gradle 의 작업 디렉터리는 {@code backend/}
     * 이지만, IDE 에서 실행하면 저장소 루트일 수 있다.</p>
     */
    private static Set<String> backendEnvironmentKeys() throws IOException {
        Path compose = locate(Path.of("infra", "compose.prod.yml"));

        try (InputStream stream = Files.newInputStream(compose)) {
            Map<String, Object> root = new Yaml().load(stream);
            @SuppressWarnings("unchecked")
            Map<String, Object> services = (Map<String, Object>) root.get("services");
            @SuppressWarnings("unchecked")
            Map<String, Object> backend = (Map<String, Object>) services.get("backend");
            @SuppressWarnings("unchecked")
            Map<String, Object> environment = (Map<String, Object>) backend.get("environment");
            return new TreeSet<>(environment.keySet());
        }
    }

    private static Path locate(Path relative) {
        Path here = Path.of("").toAbsolutePath();
        for (Path candidate = here; candidate != null; candidate = candidate.getParent()) {
            Path found = candidate.resolve(relative);
            if (Files.exists(found)) {
                return found;
            }
        }
        throw new IllegalStateException(
            "could not find " + relative + " above " + here
                + "; this test compares application.yml with the deployed compose file");
    }
}
