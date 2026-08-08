package com.ssafy.bomi.scenario.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 활성 시나리오 타임아웃 워치독 설정 (prefix {@code bomi.scenario-timeout}).
 *
 * <p>{@code ScenarioStartGuard}는 타입을 가리지 않고 이 어르신에게 활성(터미널이
 * 아닌) 시나리오가 하나라도 있으면 새 시나리오를 막는다 — 로봇이 한 대뿐이라서다.
 * 정상 흐름에서는 각 이벤트(도착, 대화 종료 등)가 시나리오를 다음 상태로 밀어주지만,
 * 그 이벤트가 오지 않으면(대화 핸드오프가 아직 로깅 스텁이거나, 신호가 유실되거나)
 * 시나리오는 활성 상태에 영원히 머물고, 그 뒤로 그 어르신의 모든 시나리오가 막힌다.</p>
 *
 * <p>이 워치독은 그 마지막 안전망이다: 활성 상태로 이 시간을 넘긴 시나리오를 강제로
 * {@code TIMED_OUT} 처리해, 다음 이벤트가 다시 시작할 수 있게 한다.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.scenario-timeout")
public class ScenarioTimeoutProperties {

    /**
     * 시나리오가 활성 상태로 이 시간을 넘기면 강제 종료한다.
     *
     * <p>현관 인사 왕복(이동→대화→복귀)은 정상적으로 몇 분 안에 끝나므로 여유를 넉넉히
     * 둔다 — 너무 짧으면 정상적으로 길어진 대화 중에 시나리오가 끊긴다. 너무 길면
     * 안전망으로서의 가치가 줄어든다.</p>
     */
    private Duration activeTimeout = Duration.ofMinutes(10);

    public Duration getActiveTimeout() {
        return activeTimeout;
    }

    public void setActiveTimeout(Duration activeTimeout) {
        this.activeTimeout = activeTimeout;
    }
}
