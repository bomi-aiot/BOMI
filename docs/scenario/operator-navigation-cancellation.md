# 운영자 내비게이션 시나리오 취소

Robot이 내비게이션 결과를 보내지 못해 Scenario와 Robot mode가 계속 활성 상태로
남았을 때 사용한다. 이 절차는 인증된 운영자만 실행할 수 있다.

## 1. 활성 내비게이션 취소

로봇 주변과 이동 경로의 물리적 안전을 먼저 확인한다.

```bash
curl -X POST \
  "https://<backend-host>/api/v1/operator/robots/bomi-AA001/active-scenario-cancellations" \
  -H "X-Operator-Shared-Secret: $OPERATOR_SHARED_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{
    "physicalSafetyConfirmed": true,
    "reason": "Jetson/Nav2 상태 확인 후 멈춘 현관 이동 시나리오 취소"
  }'
```

성공하면 Backend는 다음 작업을 하나의 트랜잭션으로 처리한다.

- 활성 `NAVIGATE`의 command ID를 대상으로 MQTT `CANCEL` 발행 예약
- Scenario를 `CANCELLED`로 종료
- Robot mode를 `SAFE_STOP`으로 변경
- 운영자, 사유, 대상 명령 및 취소 명령을 감사 테이블에 기록

같은 요청을 다시 보내 활성 Scenario가 없으면
`NO_OP_NO_ACTIVE_SCENARIO`를 반환한다. 활성 Scenario가 여러 개이거나 내비게이션
명령이 없는 Scenario이면 자동으로 상태를 바꾸지 않고 `409`를 반환한다.

## 2. 정지 확인 후 IDLE 복구

Jetson/Nav2에서 로봇이 실제로 정지한 것을 확인한 뒤 기존 복구 API를 호출한다.

```bash
curl -X POST \
  "https://<backend-host>/api/v1/operator/robots/bomi-AA001/mode-recoveries" \
  -H "X-Operator-Shared-Secret: $OPERATOR_SHARED_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{
    "physicalSafetyConfirmed": true,
    "reason": "CANCEL 처리 및 Robot 정지 확인"
  }'
```

이 호출이 성공하면 Robot mode가 `SAFE_STOP`에서 `IDLE`로 바뀐다. 취소 API와
복구 API를 한 번에 합치지 않은 이유는 MQTT 취소 명령 발행과 실제 모터 정지 확인
사이에 시간 차이가 있을 수 있기 때문이다.
