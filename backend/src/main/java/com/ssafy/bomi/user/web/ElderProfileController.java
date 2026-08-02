package com.ssafy.bomi.user.web;

import com.ssafy.bomi.user.web.dto.ElderProfileDto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 어르신 프로필(기본정보) 조회 API. 단일 어르신 전제(P0)라 경로에 elderId 없음.
 * 접두: {@code /api/v1/elders/profile} (FE API_ENDPOINTS.elderProfile 과 일치).
 */
@RestController
@RequestMapping("/api/v1/elders")
public class ElderProfileController {

    private final ElderProfileService service;

    public ElderProfileController(ElderProfileService service) {
        this.service = service;
    }

    @GetMapping("/profile")
    public ElderProfileDto getProfile() {
        return service.getProfile();
    }
}
