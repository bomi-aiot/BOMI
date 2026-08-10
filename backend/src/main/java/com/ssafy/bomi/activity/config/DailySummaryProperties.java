package com.ssafy.bomi.activity.config;

import java.time.LocalTime;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.stereotype.Component;

/**
 * 보호자 일일 요약 발송 설정 (prefix {@code bomi.daily-summary}, S15P11E102 G2).
 *
 * <p><b>왜 발송 시각이 프로퍼티인가.</b> 코드에 박으면 시연 현장에서 "지금 한 번
 * 보내 보자"를 하려고 재배포를 해야 한다. 그리고 발송 시각은 한 번 정하고 잊는 값이
 * 아니다 — 보호자가 출근길에 읽는 집과 아침을 늦게 시작하는 집이 다르다.</p>
 *
 * <p><b>발송 창 = {@code [sendAtLocal, sendAtLocal + windowMinutes)} — 어르신 로컬
 * 기준이다.</b> 창을 두는 이유는 {@code MedicationReminderScheduler} 와 같다: 틱 한 번을
 * 놓쳤다고 그날 요약이 통째로 사라지면 안 된다. 30분 창 × 1분 폴링이면 재기동 한 번은
 * 남은 틱이 흡수한다. 반대로 창을 지나친 하루는 <b>영영 발송되지 않는다</b> — 다음 날
 * 창은 새 {@code metricDate} 를 보기 때문이다. 아침 내내 백엔드가 죽어 있었던 날의
 * 요약은 운영자 수동 트리거(별도 티켓) 없이는 나가지 않는다.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.daily-summary")
public class DailySummaryProperties {

    /**
     * 발송 잡 자체를 켤지. 기본 <b>true</b>.
     *
     * <p>{@code EmbeddingProperties}/{@code LlmProperties} 가 기본 꺼짐인 이유는 과금되는
     * 외부 API 라서다. 이 잡은 DB 만 만진다 — 그래서
     * {@code ConversationLifecycleProperties.sweepEnabled} 와 같은 기본 켜짐이다.
     * 기본을 꺼짐으로 두면 배포 env 에 한 줄을 빠뜨렸을 때 "구현은 다 됐는데 아무도
     * 부르지 않아 보호자가 요약을 한 번도 못 받는" 상태로 정확히 되돌아간다. 그게 바로
     * 이 티켓이 고치는 문제다.</p>
     */
    private boolean enabled = true;

    /**
     * 어르신 <em>로컬</em> 발송 시각. 기본 08:00.
     *
     * <p><b>왜 아침인가, 왜 일간 요약 <em>생성</em>(현지 새벽 2~3시)과 다른 시각인가</b>
     * — {@code DailySummaryScheduler} 클래스 자바독에 이유 세 가지를 적어 뒀다. 요약하면:
     * 집계는 DB 만 만지는 일이고 발송은 사람에게 닿는 일이라 옳은 시각이 다르다.</p>
     *
     * <p>{@code @DateTimeFormat} 을 명시하는 이유 — {@code "08:00"} 문자열은 Boot 의
     * 일반 변환기로도 붙지만, 그 경로는 컨버터 등록 순서에 의존한다. 명시해 두면 바인딩
     * 실패가 기동 시점에 즉시 터진다(조용한 실패가 아니다).</p>
     */
    @DateTimeFormat(iso = DateTimeFormat.ISO.TIME)
    private LocalTime sendAtLocal = LocalTime.of(8, 0);

    /**
     * 발송 창의 길이(분). 기본 30.
     *
     * <p>키우면 죽어 있던 아침을 더 많이 복구하지만, 늦은 오전에 도착하는 "어제 요약"의
     * 가치도 같이 떨어진다.</p>
     */
    private long windowMinutes = 30;

    /**
     * 폴링 주기(ms). 기본 1분 — {@code MedicationReminderScheduler} 와 같다.
     *
     * <p>창(30분) 안에서 이 값이 곧 재시도 횟수다. 키우면 재시도 기회가 줄고, 줄이면
     * 아무 이득 없이 조회만 늘어난다(발송 자체는 하루 한 번으로 막혀 있다).</p>
     */
    private long tickIntervalMillis = 60_000;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public LocalTime getSendAtLocal() {
        return sendAtLocal;
    }

    public void setSendAtLocal(LocalTime sendAtLocal) {
        this.sendAtLocal = sendAtLocal;
    }

    public long getWindowMinutes() {
        return windowMinutes;
    }

    public void setWindowMinutes(long windowMinutes) {
        this.windowMinutes = windowMinutes;
    }

    public long getTickIntervalMillis() {
        return tickIntervalMillis;
    }

    public void setTickIntervalMillis(long tickIntervalMillis) {
        this.tickIntervalMillis = tickIntervalMillis;
    }
}
