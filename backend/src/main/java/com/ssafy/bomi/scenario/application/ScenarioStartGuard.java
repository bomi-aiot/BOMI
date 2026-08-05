package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * 새 시나리오를 시작해도 되는지 판정하는 교통정리 담당.
 *
 * <p>모든 오케스트레이터는 시나리오를 만들기 전에 여기에 먼저 묻는다. 두 가지를
 * 검사한다.</p>
 *
 * <ol>
 *   <li><b>활성 시나리오 검사</b> — 이 어르신에게 진행 중(터미널이 아닌) 시나리오가
 *       하나라도 있으면 막는다. 타입을 가리지 않는다: 로봇은 한 대뿐이라, 귀가 인사
 *       중에 산책이 시작되면 로봇이 두 명령 사이에서 찢어진다.</li>
 *   <li><b>쿨다운 검사</b> — 같은 타입의 시나리오가 최근 {@code cooldown} 안에
 *       COMPLETED 로 끝났으면 막는다. 온습도처럼 연속으로 들어오는 신호가 "더운 방은
 *       5분 뒤에도 덥다"는 이유로 같은 시나리오를 무한 생성하는 것을 막는다.
 *       문 열림처럼 사건 자체가 이산적인 트리거는 {@link Duration#ZERO}를 넘겨
 *       이 검사를 끈다 — 30분 안에 두 번 외출하고 돌아오는 것은 정상이다.</li>
 * </ol>
 *
 * <p>쿨다운이 COMPLETED 만 보는 이유: FAILED/TIMED_OUT 뒤의 재시도는 막을 이유가
 * 없다. 실패했다고 30분간 안부를 안 물으면 안 된다.</p>
 */
@Component
public class ScenarioStartGuard {

    /** 막힌 이유. 호출부가 로그에 남겨 "왜 로봇이 안 움직였나"를 답할 수 있게 한다. */
    public enum BlockReason {
        /** Robot assignment points at no registered senior row. */
        SENIOR_NOT_FOUND,
        /** 이 어르신에게 진행 중인 시나리오가 이미 있다 (타입 무관). */
        ACTIVE_SCENARIO_EXISTS,
        /** 같은 타입 시나리오가 쿨다운 안에 완료됐다. */
        COOLDOWN_ACTIVE
    }

    private final ScenarioRepository scenarioRepository;
    private final AppUserRepository appUserRepository;

    public ScenarioStartGuard(
        ScenarioRepository scenarioRepository,
        AppUserRepository appUserRepository
    ) {
        this.scenarioRepository = scenarioRepository;
        this.appUserRepository = appUserRepository;
    }

    /**
     * 시작 가능 여부를 판정한다.
     *
     * @param seniorId 대상 어르신
     * @param type     시작하려는 시나리오 타입 (쿨다운은 같은 타입끼리만 비교)
     * @param cooldown 같은 타입 완료 후 재시작 금지 시간. {@link Duration#ZERO}면 쿨다운 검사 없음
     * @return 비어 있으면 시작해도 된다. 값이 있으면 그 이유로 막혔다
     */
    public Optional<BlockReason> check(UUID seniorId, ScenarioType type, Duration cooldown) {
        // Every starter takes the same senior-row mutex before exists-then-insert.
        // The partial unique index remains the final cross-process invariant.
        if (appUserRepository.findByIdForUpdate(seniorId).isEmpty()) {
            return Optional.of(BlockReason.SENIOR_NOT_FOUND);
        }
        if (scenarioRepository.existsBySeniorIdAndFinalStatusIn(
                seniorId, ScenarioStatus.activeStatuses())) {
            return Optional.of(BlockReason.ACTIVE_SCENARIO_EXISTS);
        }
        if (!cooldown.isZero() && scenarioRepository
                .existsBySeniorIdAndScenarioTypeAndFinalStatusAndUpdatedAtAfter(
                    seniorId, type, ScenarioStatus.COMPLETED, OffsetDateTime.now().minus(cooldown))) {
            return Optional.of(BlockReason.COOLDOWN_ACTIVE);
        }
        return Optional.empty();
    }
}
