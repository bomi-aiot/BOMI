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
     * 만료를 모두 확인한다"고만 말하고 구체적인 일수는 정하지 않았다. 30일은 요약·
     * 사실추출·감사 목적을 넉넉히 커버하면서도 무기한 보관은 아닌 절충값이다.</p>
     *
     * <p><b>이 값은 더 이상 예정 시각을 적어 두기만 하는 값이 아니다.</b> 오래도록
     * {@code conversation.raw_messages_expires_at} 을 채우기만 하고 읽는 코드가 저장소에
     * 하나도 없었는데, 이제 {@code ConversationRawPurgeService} 가 그 컬럼의 소비자다 —
     * 여기서 정한 일수가 지나면 발화가 <b>영구히</b> 삭제된다. 다만 그 잡은
     * {@link #purgeEnabled} 가 켜져 있을 때만 존재하므로, 이 값을 줄이는 것만으로는
     * 아무것도 지워지지 않는다(두 값을 함께 봐야 한다).</p>
     */
    private int rawRetentionDays = 30;

    /** 유휴시간 스윕 잡 자체를 켤지. 기본 true — 위 클래스 설명 참고. */
    private boolean sweepEnabled = true;

    /** 스윕 주기(ms). 30분 유휴시간 대비 1분이면 충분히 촘촘하다. */
    private long sweepIntervalMillis = 60_000;

    /**
     * 보존기간이 지난 원본 발화를 <b>영구 삭제</b>하는 잡을 켤지 (ERD §4, 시나리오 31·32).
     *
     * <p><b>★ 이 클래스에서 유일하게 기본값이 꺼짐인 값이다.</b> 위 {@link #sweepEnabled}
     * 이 켜져 있는 이유("돈이 안 들고, 꺼져 있으면 문제가 되돌아온다")는 여기엔 적용되지
     * 않는다 — 이쪽은 되돌릴 수 없다. {@code conversation_message} 에는 백업도, 소프트
     * 삭제도, 감사 테이블도 없어서 술어가 한 줄만 틀려도 어르신의 대화가 조용히 사라지고
     * 그 사실을 알려 주는 것이 아무것도 없다. 그래서 "켜는 것"을 의도적인 행위로 만든다:
     * {@code ConversationRawPurgeSweeper} 는 이 값이 명시적으로 {@code true} 일 때만
     * <b>빈 자체가 생성된다</b>({@code EmbeddingSyncScheduler} 선례 — 위험한 기능은
     * "매 틱 스스로 skip 한다"가 아니라 "틱 자체가 없다"여야 로그를 안 보고도 확신할 수
     * 있다). 저기는 돈이 걸려 있었고 여기는 되돌릴 수 없는 삭제다.</p>
     */
    private boolean purgeEnabled = false;

    /**
     * 한 번의 실행에서 발화를 지울 대화 수 상한.
     *
     * <p>{@code EmbeddingSyncService} 의 배치 상한과 문법은 같지만 의미가 다르다 —
     * 저기는 지출 상한이고, 여기는 <b>한 사고의 폭 상한</b>이다. 선행조건 술어를 잘못
     * 짠 채 배포하더라도 첫 실행에서 사라지는 대화가 이 수를 넘지 않으므로, 다음 실행
     * 전에 알아채면 나머지는 살아 있다. 상한이 상한이려면 선별이 전부 SQL 술어여야
     * 한다(서비스에서 걸러내면 이 값이 "지운 수"가 아니라 "검사한 수"가 된다).</p>
     */
    private int purgeBatchSize = 200;

    /**
     * 삭제 잡 주기(ms). 기본 1시간.
     *
     * <p>보존기간의 단위가 일(day)이라 분 단위로 촘촘하게 돌 이유가 없다. 자주 돌수록
     * "잘못 켰다"를 알아채고 끄기까지 지워지는 양만 늘어난다.</p>
     */
    private long purgeIntervalMillis = 3_600_000;

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

    public boolean isPurgeEnabled() {
        return purgeEnabled;
    }

    public void setPurgeEnabled(boolean purgeEnabled) {
        this.purgeEnabled = purgeEnabled;
    }

    public int getPurgeBatchSize() {
        return purgeBatchSize;
    }

    public void setPurgeBatchSize(int purgeBatchSize) {
        this.purgeBatchSize = purgeBatchSize;
    }

    public long getPurgeIntervalMillis() {
        return purgeIntervalMillis;
    }

    public void setPurgeIntervalMillis(long purgeIntervalMillis) {
        this.purgeIntervalMillis = purgeIntervalMillis;
    }
}
