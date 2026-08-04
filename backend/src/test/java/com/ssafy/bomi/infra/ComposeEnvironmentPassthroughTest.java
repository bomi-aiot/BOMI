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
import java.util.List;
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
    private static final Map<String, String> INTENTIONALLY_NOT_FORWARDED = Map.ofEntries(
        Map.entry("MQTT_BROKER_HOST",
            "MQTT_BROKER_URL 의 기본값을 조립하는 데만 쓰인다. compose 는 완성된 URL 을 직접 넘긴다"),
        Map.entry("MQTT_BROKER_PORT",
            "MQTT_BROKER_HOST 와 함께 기본 URL 을 만드는 조각이다. URL 을 넘기므로 도달할 필요가 없다"),
        Map.entry("QDRANT_DIMENSIONS",
            "차원을 바꾸면 컬렉션을 다시 만들어야 하고 전량 재색인이다. env 를 고쳐서 되는 일이 아니다"),
        Map.entry("EMBEDDING_DIMENSIONS",
            "모델의 출력 차원이므로 코드 상수에 가깝다. 바꾸려면 컬렉션부터 다시 만들어야 한다"),
        Map.entry("UPSTAGE_PASSAGE_MODEL",
            "모델을 바꾸면 기존 벡터 전체가 무효다(벡터 공간이 다르다). 의도된 재배포 작업이다"),
        Map.entry("UPSTAGE_QUERY_MODEL",
            "passage 모델과 짝을 유지해야 한다. 한쪽만 바꿀 수 있으면 검색이 조용히 나빠진다"),
        Map.entry("UPSTAGE_BASE_URL",
            "API 엔드포인트가 바뀌는 것은 배포 사건이고, 운영 중 전환할 대상이 아니다"),
        Map.entry("QDRANT_TIMEOUT_MILLIS",
            "턴 지연 예산(약 2초)에서 나온 값이다. 늘리는 것은 예산을 다시 정하는 판단이다"),
        Map.entry("EMBEDDING_TIMEOUT_MILLIS",
            "질의 임베딩이 턴 예산 안에 있다. 이 값을 늘리면 어르신이 더 오래 침묵을 듣는다"),
        Map.entry("EMBEDDING_SYNC_INTERVAL_MILLIS",
            "배치 간격이다. 급하면 sync-enabled 를 끄면 되므로 간격만 따로 조정할 이유가 없다"),
        // 대화 요약 생성형 LLM (S15P11E102-254). enabled/api-key/max-calls-per-run 셋만
        // 넘긴다 — embedding 이 이미 정한 "과금 스위치·키·지출 상한만 운영 다이얼"
        // 기준을 그대로 따른다.
        Map.entry("LLM_BASE_URL",
            "API 엔드포인트가 바뀌는 것은 배포 사건이다. UPSTAGE_BASE_URL 과 같은 판단이다"),
        Map.entry("LLM_MODEL",
            "모델을 바꾸면 응답 품질·비용·말투가 달라진다. 신중한 배포 판단이지 운영 중 즉흥 전환 대상이 아니다"),
        Map.entry("LLM_TIMEOUT_MILLIS",
            "요약 스윕은 턴 예산(약 2초) 밖에서 돈다(GeminiTextGenerator 참고). 늦장 호출 대응은 재배포로 다룬다"),
        Map.entry("LLM_MAX_OUTPUT_TOKENS",
            "요약 길이 정책이다. 프롬프트·저장 형태와 함께 바뀌어야 하므로 배포 판단이다"),
        Map.entry("LLM_MAX_SUMMARY_MESSAGES",
            "프롬프트에 실을 발화 수 상한이다. 프롬프트 설계와 함께 바뀌어야 하는 값이다"),
        Map.entry("LLM_SWEEP_INTERVAL_MILLIS",
            "배치 간격이다. 급하면 LLM_ENABLED 를 끄면 스윕 빈 자체가 사라지므로 간격만 따로 조정할 이유가 없다"),
        // 대화 경계 (S15P11E102-254). idle-timeout 만 넘긴다 — 완료 조건이 명시한
        // 30분을 현장에서 조정할 수 있어야 하는 값이라 SCENARIO_ACTIVE_TIMEOUT 과
        // 같은 기준으로 뽑았다. 나머지는 재배포 없이 바꿀 운영상의 이유가 없다.
        Map.entry("CONVERSATION_RAW_RETENTION_DAYS",
            "삭제 잡이 아직 없다(이 티켓 범위 밖). 삭제 잡이 생기면 그때 함께 노출한다"),
        Map.entry("CONVERSATION_LIFECYCLE_SWEEP_ENABLED",
            "끄면 이 티켓이 고치는 문제(대화가 영원히 OPEN)로 되돌아간다. 끌 이유가 있다면 재배포로 다룰 사고 대응이다"),
        Map.entry("CONVERSATION_LIFECYCLE_SWEEP_INTERVAL_MILLIS",
            "배치 간격이다. 유휴시간(30분) 대비 기본 1분이면 촘촘하다. 급하면 sweep-enabled 를 끄면 된다"));

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
    // ─────────────────────────────────────────────────────────────────────────
    // 볼륨 바인드 소스가 배포 스크립트의 검증 목록과 어긋나지 않는가
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * 배포 스크립트가 검증하지 않는 바인드 소스. <b>각 줄에 이유가 있어야 한다.</b>
     *
     * <p>기준은 "이 값이 {@code production.env} 에서 오는가"다. Jenkins 가 실행 시점에
     * 넣어 주는 값은 배포 스크립트가 env 파일에서 읽을 수 없으므로 검증할 수 없다.</p>
     */
    private static final Map<String, String> BIND_SOURCES_NOT_GUARDED = Map.of(
        "BOMI_SOURCE_DIR",
        "production.env 에 없다. Jenkins 가 $WORKSPACE 로 넣어 주고 compose 는 기본값을 쓴다",
        "BOMI_SECRETS_DIR",
        "production.env 에 없다. compose 의 기본값(/home/ubuntu/bomi/secrets)을 쓴다");

    @Test
    @DisplayName("★ compose 의 바인드 소스가 전부 배포 스크립트에서 검증되거나, 이유가 있어야 한다")
    void everyBindMountSourceIsGuarded() throws IOException {
        Set<String> sources = bindMountSourceVariables();
        Set<String> guarded = guardedVariables();

        Set<String> unguarded = new TreeSet<>(sources);
        unguarded.removeAll(guarded);
        unguarded.removeAll(BIND_SOURCES_NOT_GUARDED.keySet());

        assertThat(unguarded)
            .as("""
                compose 가 바인드 마운트의 '왼쪽'에 쓰는 변수인데 배포 스크립트가                 절대 경로인지 확인하지 않는다. 값이 경로가 아니면 compose 는 첫 조각을                 '이름 있는 볼륨'으로 읽고, 오류에 변수 이름이 나오지 않는다                 (실제로 QDRANT_DATA_DIR 에서 겪었다). deploy-common.sh 의                 initialize_deploy 에 require_absolute_path 를 추가하거나, 검증하지                 않는 이유를 BIND_SOURCES_NOT_GUARDED 에 적는다: %s""", unguarded)
            .isEmpty();
    }

    @Test
    @DisplayName("검증하지 않기로 한 바인드 소스에는 이유가 적혀 있다")
    void everyUnguardedBindSourceCarriesAReason() {
        BIND_SOURCES_NOT_GUARDED.forEach((name, reason) ->
            assertThat(reason.length())
                .as("%s 를 검증하지 않는 이유가 너무 짧다", name)
                .isGreaterThan(20));
    }

    @Test
    @DisplayName("★ Qdrant 저장소는 호스트 경로를 받지 않는다 — named volume 이다")
    void theQdrantStoreDoesNotAskForAHostPath() throws IOException {
        /*
         * ★★ 이 티켓이 겪은 사고의 근본 수정이다. 값을 검증하는 대신 물어보지 않는다.
         *
         * 되돌아가려는 사람이 있으면 이 테스트가 먼저 실패한다. 그때 읽어야 하는 것:
         * 이 볼륨은 파생 인덱스이고 백업 대상이 아니며 부기 컬럼으로 전량 재색인된다.
         * 사람이 위치를 알아야 할 운영상의 이유가 없다.
         */
        assertThat(bindMountSourceVariables())
            .as("QDRANT_DATA_DIR 이 돌아왔다. 값 검증으로는 '/qdrant'(컨테이너 경로)나 "
                + "postgres 경로 복사 같은 실수를 잡지 못한다")
            .doesNotContain("QDRANT_DATA_DIR");

        assertThat(Files.readString(locate(Path.of("infra", "compose.prod.yml"))))
            .contains("qdrant-storage:/qdrant/storage");
    }

    /**
     * 바인드 마운트의 '소스' 쪽에 쓰인 {@code ${VAR}} 이름들.
     *
     * <p>YAML 을 파싱해서 {@code services.*.volumes} 만 본다. 처음에는 줄 단위로
     * {@code "- ${"} 를 찾았는데 {@code group_add:} 의 {@code - ${DOCKER_GID:?...}} 가
     * 걸렸다 — 항목이 콜론을 포함한다는 이유만으로 볼륨처럼 보였다. 파서가 이미
     * 있으므로 추측할 이유가 없다.</p>
     *
     * <p>소스만 본다. {@code JENKINS_HOME_DIR} 은 콜론 양쪽에 쓰이는데, 잘못된 값이
     * 문제를 만드는 것은 왼쪽이다.</p>
     */
    private static Set<String> bindMountSourceVariables() throws IOException {
        Path compose = locate(Path.of("infra", "compose.prod.yml"));
        Set<String> names = new TreeSet<>();

        try (InputStream stream = Files.newInputStream(compose)) {
            Map<String, Object> root = new Yaml().load(stream);
            @SuppressWarnings("unchecked")
            Map<String, Object> services = (Map<String, Object>) root.get("services");

            for (Object service : services.values()) {
                @SuppressWarnings("unchecked")
                Object volumes = ((Map<String, Object>) service).get("volumes");
                if (!(volumes instanceof List<?> entries)) {
                    continue;
                }
                for (Object entry : entries) {
                    if (entry instanceof String mount) {
                        addSourceVariable(mount, names);
                    }
                }
            }
        }
        return names;
    }

    /**
     * 마운트 한 줄의 소스 쪽에서 변수 이름을 뽑는다.
     *
     * <p>{@code "${VAR:?msg}:/container/path"} 의 소스는 닫는 중괄호까지다. 콜론으로
     * 그냥 쪼개면 {@code :?} 안의 콜론에서 잘린다.</p>
     */
    private static void addSourceVariable(String mount, Set<String> names) {
        if (!mount.startsWith("${")) {
            return;   // 이름 있는 볼륨이거나 상대 경로다. 검증 대상이 아니다.
        }
        int close = mount.indexOf('}');
        if (close < 0) {
            return;
        }
        Matcher matcher = PLACEHOLDER.matcher(mount.substring(0, close + 1));
        if (matcher.find()) {
            names.add(matcher.group(1));
        }
    }

    /** {@code initialize_deploy} 가 require_absolute_path 로 검증하는 변수들. */
    private static Set<String> guardedVariables() throws IOException {
        String script = Files.readString(
            locate(Path.of("scripts", "deploy", "deploy-common.sh")), StandardCharsets.UTF_8);

        Set<String> guarded = new TreeSet<>();
        Matcher matcher = Pattern.compile("require_absolute_path\s+([A-Z_][A-Z0-9_]*)")
            .matcher(script);
        while (matcher.find()) {
            guarded.add(matcher.group(1));
        }
        return guarded;
    }
}
