package com.ssafy.bomi.docs;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/**
 * Serves the AsyncAPI contract as JSON so the docs page can render it.
 *
 * <p><b>Why a conversion endpoint instead of shipping a second file.</b> The YAML is the
 * single source — hand-edited, commented, and consistent with the OpenAPI specs next to
 * it. Committing a JSON copy alongside it would give us two files to keep in step, which
 * {@code docs/api/README.md} §6 exists to prevent.</p>
 *
 * <p><b>Why the browser cannot read the YAML directly.</b> Production Nginx sends
 * {@code Content-Security-Policy: script-src 'self'}, so no CDN YAML parser can load, and
 * there is no Node build step here to vendor one. Converting on the server side costs one
 * dependency we already have (snakeyaml, via Spring Boot) and no new moving parts.</p>
 */
@RestController
@Tag(
        name = "AsyncAPI Spec",
        description = "MQTT 계약 스펙을 JSON 으로 변환해 제공합니다 — 문서 렌더러(/asyncapi/)가 호출합니다.")
public class AsyncApiSpecController {

    private static final String SPEC_PATH = "static/openapi/bomi-mqtt.asyncapi.yaml";

    /** Parsed once. The spec is a build artifact — it cannot change while the app runs. */
    private volatile Map<String, Object> cached;

    @GetMapping(value = "/openapi/bomi-mqtt.asyncapi.json", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "MQTT AsyncAPI 계약 (JSON)")
    public Map<String, Object> asyncApiSpec() throws IOException {
        Map<String, Object> local = cached;
        if (local == null) {
            local = load();
            cached = local;
        }
        return local;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> load() throws IOException {
        ClassPathResource resource = new ClassPathResource(SPEC_PATH);
        try (InputStream in = resource.getInputStream()) {
            String text = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            Yaml yaml = new Yaml(new SafeConstructor(new LoaderOptions()));
            Object loaded = yaml.load(text);
            if (!(loaded instanceof Map)) {
                throw new IllegalStateException(SPEC_PATH + " 최상위가 매핑이 아닙니다.");
            }
            return (Map<String, Object>) loaded;
        }
    }
}
