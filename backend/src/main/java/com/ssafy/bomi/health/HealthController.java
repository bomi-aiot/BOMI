package com.ssafy.bomi.health;

import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.Instant;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@Tag(name = "Health", description = "헬스 체크 — 운영·모니터링이 호출합니다.")
public class HealthController {
    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("service", "bomi-backend", "status", "UP", "timestamp", Instant.now());
    }
}
