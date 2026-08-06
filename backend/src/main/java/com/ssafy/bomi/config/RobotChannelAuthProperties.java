package com.ssafy.bomi.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 로봇 채널 공유 비밀키 설정 (S15P11E102-307).
 *
 * <p><b>왜 존재하는가.</b> 지금 백엔드에는 인증 계층이 전혀 없다.
 * {@code /api/v1/robot/**}, {@code /api/v1/seniors/**} 아래 API는 익명 호출자에게도
 * 그대로 열려 있어서, 이름·복약 스케줄·회피 주제(CLAUDE.md §8) 같은 민감 정보를
 * 아무나 읽을 수 있고 가짜 T1 보호자 알림(CLAUDE.md §9)도 만들 수 있었다. 이
 * 설정은 그 구멍을 막는 서블릿 필터({@link RobotChannelAuthFilter})가 무엇과
 * 비교할지를 담는다.</p>
 *
 * <p><b>비어 있으면 통과시킨다.</b> {@code embedding/config/EmbeddingProperties}의
 * {@code enabled && !isBlank()} 패턴을 그대로 따른다 — 로컬 개발과 기존 MockMvc
 * 테스트가 시크릿 없이도 그대로 통과해야 하는 것이 이 티켓의 핵심 요구사항이고,
 * Spring Security 스타터를 새로 넣지 않기로 한 이유이기도 하다(넣으면 기본
 * 필터체인이 켜져 actuator·swagger·기존 테스트가 한꺼번에 401로 돈다).</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.robot-channel")
public class RobotChannelAuthProperties {

    /** 비어 있으면(기본값) 인증 필터가 아무 요청도 막지 않는다. */
    private String sharedSecret = "";

    public String getSharedSecret() {
        return sharedSecret;
    }

    public void setSharedSecret(String sharedSecret) {
        this.sharedSecret = sharedSecret == null ? "" : sharedSecret.trim();
    }

    /** 필터가 실제로 검사를 수행해야 하는지. 시크릿이 비어 있으면 게이트 자체가 꺼진 것으로 본다. */
    public boolean isUsable() {
        return !sharedSecret.isBlank();
    }
}
