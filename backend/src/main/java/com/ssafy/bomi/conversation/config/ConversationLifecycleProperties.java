package com.ssafy.bomi.conversation.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 대화 경계(시작·종료) 판단 설정 (prefix {@code bomi.conversation-lifecycle},
 * S15P11E102-254).
 *
 * <p>이 값들은 돈이 드는 기능이 아니다 — 유휴시간 초과로 대화를 닫는 것은 DB 갱신
 * 하나일 뿐, 외부 API 호출이 없다. 그래서 {@code EmbeddingProperties}·{@code LlmProperties}
 * 와 달리 {@link #sweepEnabled} 의 기본값은 <b>true</b> 다: 이 기능이 꺼져 있으면 모든
 * 대화가 영원히 OPEN 으로 남는다는, 이 티켓이 고치려는 바로 그 문제로 되돌아간다.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.conversation-lifecycle")
public class ConversationLifecycleProperties {

    /**
     * 이만큼 조용하면 대화가 끝난 것으로 본다.
     *
     * <p>완료 조건이 명시한 값(30분)이 기본값이다. CLAUDE.md §15 의 침묵 사다리와는
     * 다른 개념이다 — 그쪽은 "안전한가"를 묻고, 이쪽은 "대화 단위를 어디서 끊을
     * 것인가"만 묻는다. 낮추면 정상적인 침묵(생각하는 중)에도 대화가 쪼개지고,
     * 올리면 실제로는 끝난 대화가 오래 OPEN 으로 남아 다음 발화가 엉뚱하게 이어붙는다.</p>
     */
    private Duration idleTimeout = Duration.ofMinutes(30);

    /**
     * 대화가 닫힌 뒤 원본 발화(conversation_message)를 지울 수 있는 시점까지의 유예(일).
     *
     * <p>ERD §4 는 "Raw 삭제 전에는 요약 생성·활성 후보 해소·확정 사실 반영·보존기간
     * 만료를 모두 확인한다"고만 말하고 구체적인 일수는 정하지 않았다 — 실제 삭제 잡은
     * 이 티켓 범위가 아니다(이 값은 그 잡이 나중에 참고할 예정 시각만 채워 둔다).
     * 30일은 요약·사실추출·감사 목적을 넉넉히 커버하면서도 무기한 보관은 아닌
     * 절충값이다.</p>
     */
    private int rawRetentionDays = 30;

    /** 유휴시간 스윕 잡 자체를 켤지. 기본 true — 위 클래스 설명 참고. */
    private boolean sweepEnabled = true;

    /** 스윕 주기(ms). 30분 유휴시간 대비 1분이면 충분히 촘촘하다. */
    private long sweepIntervalMillis = 60_000;

    public Duration getIdleTimeout() {
        return idleTimeout;
    }

    public void setIdleTimeout(Duration idleTimeout) {
        this.idleTimeout = idleTimeout;
    }

    public int getRawRetentionDays() {
        return rawRetentionDays;
    }

    public void setRawRetentionDays(int rawRetentionDays) {
        this.rawRetentionDays = rawRetentionDays;
    }

    public boolean isSweepEnabled() {
        return sweepEnabled;
    }

    public void setSweepEnabled(boolean sweepEnabled) {
        this.sweepEnabled = sweepEnabled;
    }

    public long getSweepIntervalMillis() {
        return sweepIntervalMillis;
    }

    public void setSweepIntervalMillis(long sweepIntervalMillis) {
        this.sweepIntervalMillis = sweepIntervalMillis;
    }
}
