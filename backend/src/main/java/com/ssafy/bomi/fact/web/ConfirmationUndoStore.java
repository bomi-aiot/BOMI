package com.ssafy.bomi.fact.web;

import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

/**
 * 직전 resolve 결과를 되돌리기 위한 인메모리 스냅샷 저장소.
 *
 * <p>P0 한정: 단일 인스턴스·세션성(재시작 시 소실). FE 목업의 undo 도 세션성이므로 동작이 일치한다.
 * 다중 인스턴스/영속 undo 가 필요해지면 audit 테이블로 대체.</p>
 */
@Component
public class ConfirmationUndoStore {

    /**
     * resolve 직전 스냅샷.
     *
     * @param previousStatus resolve 이전 상태(되돌릴 목표)
     * @param targetDomain   materialize 로 생성된 대상 도메인(MEMORY/CARE_RECORD), 없으면 null
     * @param targetId       생성된 대상 row id, 없으면 null
     */
    public record Snapshot(FactCandidateStatus previousStatus, String targetDomain, UUID targetId) {
    }

    private final ConcurrentMap<UUID, Snapshot> snapshots = new ConcurrentHashMap<>();

    public void save(UUID candidateId, Snapshot snapshot) {
        snapshots.put(candidateId, snapshot);
    }

    /** 스냅샷을 꺼내고 제거한다(1회성 undo). 없으면 null. */
    public Snapshot pop(UUID candidateId) {
        return snapshots.remove(candidateId);
    }
}
