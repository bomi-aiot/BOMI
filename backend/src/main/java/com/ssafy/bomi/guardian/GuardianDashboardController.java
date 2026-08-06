package com.ssafy.bomi.guardian;

import com.ssafy.bomi.guardian.dto.DashboardResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 가디언 웹 대시보드 API. 단일 어르신 전제(P0)라 경로에 elderId 가 없다.
 * 전체 경로: {@code GET /api/v1/guardian/dashboard} (FE API_BASE_URL 기본값 "/api").
 */
@RestController
@RequestMapping("/api/v1/guardian")
@Tag(name = "Guardian Dashboard", description = "보호자 대시보드 — 가디언웹이 호출합니다.")
public class GuardianDashboardController {

    private final DashboardService dashboardService;

    public GuardianDashboardController(DashboardService dashboardService) {
        this.dashboardService = dashboardService;
    }

    @GetMapping("/dashboard")
    public DashboardResponse getDashboard() {
        return dashboardService.getDashboard();
    }
}
