package com.ssafy.bomi.scenario.domain;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Current coarse status of a {@link Scenario}.
 *
 * <p>Values follow the {@code SCENARIO_ENUM} code dictionary of the MVP ERD.
 * Although the column is named {@code final_status}, it holds the <b>current</b>
 * status throughout the flow, and the terminal values ({@link #COMPLETED},
 * {@link #FAILED}, {@link #CANCELLED}, {@link #TIMED_OUT}) are simply the states
 * that end it. {@link #RECEIVED} is the starting status.</p>
 *
 * <p>The linear progression here is the {@code HOMECOMING} happy path. Allowed
 * transitions are enforced by {@link Scenario}.</p>
 */
public enum ScenarioStatus {
    RECEIVED,
    MOVING_TO_ENTRANCE,
    CHECKING_INTERACTION,
    CONVERSING,
    RETURN_DECISION,
    RETURNING_TO_DEFAULT,
    COMPLETED,
    FAILED,
    CANCELLED,
    TIMED_OUT;

    /** Terminal statuses admit no further transition. */
    public boolean isTerminal() {
        return this == COMPLETED || this == FAILED || this == CANCELLED || this == TIMED_OUT;
    }

    /**
     * 진행 중(터미널이 아닌) 상태의 집합.
     *
     * <p>"이 어르신에게 지금 돌고 있는 시나리오가 있는가"를 물을 때 쓴다. 상태가
     * 늘어나도 이 목록을 따로 고칠 필요가 없도록 {@link #isTerminal()}에서 유도한다.</p>
     */
    public static Set<ScenarioStatus> activeStatuses() {
        return Arrays.stream(values())
            .filter(status -> !status.isTerminal())
            .collect(Collectors.toUnmodifiableSet());
    }
}
