# RAG·임베딩·Qdrant 운영 절차

이 문서는 `memory`와 `conversation_summary`가 권위 데이터인 PostgreSQL과 파생
인덱스인 Qdrant를 안전하게 활성화·복구하는 절차다. Qdrant 볼륨은 백업 원장이
아니며, 삭제하거나 다시 만드는 작업은 반드시 PostgreSQL 백업과 변경 승인을 먼저
확보한다.

## 1. 운영 계약

- 기본값은 `EMBEDDING_ENABLED=false`, `EMBEDDING_SYNC_ENABLED=false`다.
- Qdrant 접속은 컨테이너 내부 고정값이다 — `QDRANT_HOST=qdrant`, `QDRANT_GRPC_PORT=6334`,
  `QDRANT_USE_TLS=false`. 호스트에 포트를 공개하지 않는다.
- 문서 코퍼스는 `DOCUMENT_CORPUS_ENABLED=true`, 리소스는
  `classpath:rag/welfare-corpus.json`(JAR 번들)이다.
- 문서 코퍼스는 애플리케이션에 번들되어 있으며 기본 활성화다. 외부 네트워크나
  임베딩 API를 호출하지 않는다.
- 대화 중 의미 검색은 PostgreSQL에서 사용자·수명주기·검증·가시성 필터를 먼저
  적용한 뒤 Qdrant 점수로 그 후보의 순위만 바꾼다.
- 저장은 `embed -> Qdrant upsert 성공 -> embedding_status=SYNCED` 순서다. Qdrant
  비가용·재시도 가능 실패·차원 불일치는 `SYNCED`를 만들지 않는다.
- 한 의미 검색 요청은 검색 후보가 있을 때 질의 임베딩을 최대 1회 호출한다. 같은
  벡터로 `memory`와 `conversation_summary`를 검색한다.
- 동기화는 한 행당 passage 임베딩 1회이며, 한 실행의 최대 호출 수는
  `EMBEDDING_SYNC_BATCH_SIZE`다. 첫 실행도 `EMBEDDING_SYNC_INTERVAL_MILLIS` 뒤다.

## 2. 활성화 전 체크리스트

1. 승인된 Upstage 키를 `/home/ubuntu/bomi/secrets/production.env`에만 저장한다.
   로그, Git, Compose 렌더링 결과에 값을 남기지 않는다.
2. `QDRANT_DIMENSIONS`, `EMBEDDING_DIMENSIONS`, 실제 모델 출력이 모두 `4096`인지
   확인한다. 모델 변경은 같은 컬렉션에 덮어쓰지 않는다.
3. 아래처럼 과금 없이 Compose 문법과 현재 상태를 확인한다.

```bash
docker compose --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml config --quiet
docker inspect --format='{{.State.Health.Status}}' bomi-qdrant
docker exec bomi-backend curl --fail --silent \
  http://localhost:8080/actuator/health/rag
```

4. PostgreSQL에서 재색인 대상 수를 확인한다. 이 값이 초기 색인의 최대 passage
   호출 수다.

```bash
docker exec -i bomi-postgres psql -U bomi -d bomi <<'SQL'
SELECT 'memory' AS kind, embedding_status, count(*)
FROM memory
WHERE lifecycle_status = 'ACTIVE' AND verification_status <> 'REJECTED'
GROUP BY embedding_status
UNION ALL
SELECT 'summary', embedding_status, count(*)
FROM conversation_summary
WHERE superseded_by_id IS NULL
GROUP BY embedding_status
ORDER BY 1, 2;
SQL
```

5. 비용 상한을 계산하고 승인한다.

```text
초기 passage 호출 상한 = PENDING + STALE + 승인하여 재시도할 FAILED 행 수
예상 동기화 실행 횟수 = ceil(호출 상한 / EMBEDDING_SYNC_BATCH_SIZE)
canary query 호출 상한 = 후보가 있는 canary 문맥 요청 수
총 API 비용 = 모델 제공자의 현재 단가 × 실제 토큰/호출량
```

단가는 변할 수 있으므로 코드나 이 문서의 숫자를 비용 근거로 사용하지 않는다.
승인 시점의 공급자 대시보드 단가와 잔액을 별도로 기록한다.

### 2.1 Docker가 없는 Windows 개발기의 무료 검증

공식 [Qdrant 1.18.3 Windows 릴리스](https://github.com/qdrant/qdrant/releases/tag/v1.18.3)의
`qdrant-x86_64-pc-windows-msvc.zip`을 별도 임시 디렉터리에 풀어 실행할 수 있다. 저장소에
바이너리·스토리지·로그를 커밋하지 않는다.

```powershell
# 저장소 밖에 풉니다. 저장소 안(tmp/ 등)에 두면 정리 대상 잔여물로 남습니다.
$qdrantDir = Resolve-Path "$env:TEMP\qdrant-1.18.3"
Start-Process -FilePath "$qdrantDir\qdrant.exe" `
  -WorkingDirectory $qdrantDir -WindowStyle Hidden
Invoke-RestMethod http://127.0.0.1:6333/collections
```

AI 브랜치는 backend 브랜치와 동시에 필요하므로 별도 worktree를 사용한다. Python은 AI
모듈의 기존 가상환경을 지정한다. 이 테스트의 임베딩은 무료 결정적 대역이며 Upstage를
호출하지 않는다.

```powershell
$env:QDRANT_HOST = "127.0.0.1"
$env:QDRANT_GRPC_PORT = "6334"
$env:BOMI_AI_PYTHON = "C:\path\to\robot\ai_chat\venv\Scripts\python.exe"
$env:BOMI_AI_CHAT_DIR = "C:\path\to\ai-worktree\robot\ai_chat"
Set-Location backend
.\gradlew.bat integrationTest --rerun-tasks
```

성공 기준은 Qdrant 어댑터·초기화 9건과 교차 모듈 RAG E2E 1건이 모두 `passed`이고
`skipped/aborted`가 0건인 것이다. (2026-08-06 기준 건수이며, 테스트가 늘면 이 숫자도
함께 고친다. 숫자보다 중요한 것은 `skipped/aborted`가 0이라는 조건이다 — 건너뛴
테스트를 통과로 읽는 것이 이 절이 막으려는 실패다.) 교차 E2E는 복지 문서 프롬프트, 대화 저장, 사실 후보,
메모리 생성, Qdrant 재색인, 다음 턴 회상을 검증한다. 종료 후 실행한 Qdrant 프로세스와
임시 스토리지는 정확한 경로·PID를 확인한 뒤 정리한다.

## 3. 초기 색인과 canary

현재 코드는 사용자별 feature flag를 제공하지 않는다. 따라서 운영 전체에 바로 켜는
방식은 안전한 사용자별 canary가 아니다. 아래 둘 중 하나를 택한다.

- 권장: 운영 데이터의 비식별 복제본과 별도 Qdrant를 사용하는 격리 환경에서 실행한다.
- 불가피한 경우: 짧은 점검 창에 허용된 테스트 사용자만 호출하고 즉시 다시 끈다.

초기 색인은 다음 순서로 수행한다.

1. `EMBEDDING_ENABLED=true`, `EMBEDDING_SYNC_ENABLED=true`, 작은
   `EMBEDDING_SYNC_BATCH_SIZE`(예: 5), 승인된 주기를 설정하고 backend만 재기동한다.
2. `bomi_embedding_billed_calls_total`, `bomi_embedding_rows`, backend 로그의
   동기화 결과를 매 주기 확인한다. `FAILED` 또는 `deferred`가 생기면 중단한다.
3. 백로그가 0이 되면 `EMBEDDING_SYNC_ENABLED=false`로 재기동한다. 질의 검색만
   유지하고 주기적 passage 과금을 막는다.
4. 허용된 테스트 사용자의 `/context` 요청에서 다음을 함께 확인한다.
   - `availability.semanticSearch=true`
   - `retrieval.semanticRequested=true`
   - `retrieval.semanticUsed=true`
   - `retrieval.fallbackReason=null`
   - 기억·요약 hit가 PostgreSQL 권한/가시성 후보 안에만 있음
5. 일반 정보 질문에서는 `documentRequested`, `documentUsed`, `documentHitCount`와
   문서의 `source`, `version`, `chunkId`, `citation`, `url`을 확인한다. 이 경로는
   유료 임베딩을 사용하지 않는다.

## 4. 관측과 경보

Nginx는 `/actuator`를 외부에 공개하지 않는다. 다음 엔드포인트는 backend 컨테이너
내부에서만 확인한다.

```bash
docker exec bomi-backend curl --fail --silent \
  http://localhost:8080/actuator/health/rag
docker exec bomi-backend curl --fail --silent \
  http://localhost:8080/actuator/prometheus
```

주요 지표는 다음과 같다.

| 목적 | Micrometer 이름 | Prometheus 이름/판단 |
|---|---|---|
| 실제 검색/폴백 | `bomi.rag.retrieval.requests`, `fallbacks` | `bomi_rag_retrieval_*`; `kind`, `outcome`, `reason` |
| hit 수/검색 지연 | `bomi.rag.retrieval.hits`, `latency` | `bomi_rag_retrieval_hits_*`, `...latency_seconds_*` |
| 하위 단계 지연 | `bomi.rag.retrieval.stage.latency` | `stage=embedding|vector_search` |
| 실제 Upstage 호출 | `bomi.embedding.billed.calls`, `call.latency` | `kind=query|passage`, `outcome` |
| 동기화 결과 | `bomi.embedding.sync.runs`, `rows` | `outcome=skipped|completed|failed|deferred` |
| DB 백로그 | `bomi.embedding.rows` | `status=pending|stale|failed|synced` |

최소 경보 기준은 운영 기준선 확보 후 조정하되, 초기에는 아래 사건을 즉시 조사한다.

- `/actuator/health/rag`가 `DEGRADED` 또는 `DOWN`
- `FAILED > 0`, `STALE/PENDING`이 예상 완료 시간 이후에도 감소하지 않음
- 의미 검색 폴백률이 5분 동안 0보다 크거나 평상시 기준선의 2배를 초과
- `vector_*_dimension_mismatch`, `embedding_failed`, `rag_health_query_failed`
- 승인한 호출 상한보다 `bomi_embedding_billed_calls_total` 증가량이 큼

## 5. 즉시 롤백

의미 검색 장애나 비용 이상 시 Qdrant 데이터는 지우지 않고 다음 두 스위치만 끈다.

```dotenv
EMBEDDING_ENABLED=false
EMBEDDING_SYNC_ENABLED=false
```

backend를 재기동한 뒤 `/actuator/health/rag`의 `semanticMode=keyword_fallback`, 문맥
응답의 `semanticUsed=false`, 명시적 `fallbackReason`을 확인한다. 키워드·중요도·
최근성 검색과 번들 문서 검색은 계속 동작한다. 코퍼스 자체가 문제인 경우에만
`DOCUMENT_CORPUS_ENABLED=false`를 추가한다.

## 6. Qdrant 유실·재색인 복구

Qdrant 볼륨 유실 후 PostgreSQL 행이 계속 `SYNCED`이면 스케줄러는 재색인하지 않는다.
복구 전 PostgreSQL 백업을 만들고, 새 Qdrant가 healthy이며 컬렉션 차원이 맞는지
확인한다. 그 다음 아래 트랜잭션으로 **검색 가능한 권위 행만** `STALE`로 바꾼다.

```sql
BEGIN;

SELECT embedding_status, count(*)
FROM memory
WHERE lifecycle_status = 'ACTIVE' AND verification_status <> 'REJECTED'
GROUP BY embedding_status;

UPDATE memory
SET embedding_status = 'STALE'
WHERE embedding_status = 'SYNCED'
  AND lifecycle_status = 'ACTIVE'
  AND verification_status <> 'REJECTED';

UPDATE conversation_summary
SET embedding_status = 'STALE'
WHERE embedding_status = 'SYNCED'
  AND superseded_by_id IS NULL;

SELECT 'memory' AS kind, count(*) AS stale_rows
FROM memory WHERE embedding_status = 'STALE'
UNION ALL
SELECT 'summary', count(*)
FROM conversation_summary WHERE embedding_status = 'STALE';

COMMIT;
```

예상 행 수가 다르면 `ROLLBACK`하고 원인을 먼저 확인한다. 이후 작은 batch로 3장의
초기 색인 절차를 수행한다. `SYNCED` 행 수와 Qdrant collection points 수가 일치하는지
비교하되, 비검색 대상 행이 DB에 남을 수 있으므로 전체 테이블 행 수와 비교하지 않는다.

## 7. 실패 유형별 조치

| 증상 | 상태/사유 | 조치 |
|---|---|---|
| Qdrant 일시 중단·upsert 실패 | 행은 `PENDING`/`STALE`, sync `deferred` | sync를 끄고 Qdrant 복구 후 재개 |
| 입력 자체 임베딩 실패 | `FAILED` | 원문/모델 원인을 고친 행만 `STALE`로 변경 후 재시도 |
| 4096 차원 불일치 | `*_dimension_mismatch`, 허위 `SYNCED` 없음 | 즉시 두 스위치 OFF, 모델·환경값 확인, 새 컬렉션으로 재색인 |
| 문서 코퍼스 로드 실패 | `document_corpus_unavailable` | 리소스 경로/배포 JAR 확인; 의미 기억 검색과 분리 대응 |
| 질의 임베딩/벡터 검색 실패 | 요청별 `fallbackReason` | 키워드 폴백 결과를 확인하고 API/Qdrant 지연 조사 |

`FAILED` 전체를 무조건 주기 재시도하지 않는다. 같은 영구 오류를 반복 과금할 수
있다. 원인이 해결되고 대상 ID와 예상 행 수를 검토한 경우에만 해당 행을 `STALE`로
변경한다.

## 8. 미해결 운영 한계

- 사용자별/비율별 semantic canary flag가 없다. 기본 활성화 전에 추가하는 것이 좋다.
- 이 저장소의 Qdrant는 파생 인덱스라 별도 백업하지 않는다. 복구 시간은 Upstage
  호출 한도와 동기화 주기에 좌우된다.
- 공식 Qdrant와 결정적 임베딩을 사용한 무료 교차 모듈 E2E는 통과했지만 CI 필수 잡은
  아직 아니다.
- 현장 음성·MQTT·유료 Upstage까지 포함한 E2E는 키와 비용 승인이 있어야 실행할 수
  있다. 무료 테스트 통과를 그 검증으로 간주하지 않는다.
