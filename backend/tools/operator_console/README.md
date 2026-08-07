# BOMI 운영자 콘솔

기존 Jetson 웨이포인트 편집기와 분리된 EC2 운영 도구다. 인증된 Backend 운영 API를
이용해 Robot 상태를 확인하고, 멈춘 내비게이션 Scenario를 취소한 뒤 실제 정지를
확인하여 Robot mode를 `IDLE`로 복구한다.

## 실행

EC2에서 Backend 컨테이너의 운영 Secret을 현재 셸로 읽고 콘솔을 실행한다. Secret
값 자체를 화면이나 로그에 출력하지 않는다.

```bash
cd /home/ubuntu/bomi/data/jenkins/workspace/bomi-integration-production/backend/tools/operator_console
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export BOMI_BACKEND_URL='http://localhost:8080'
export OPERATOR_SHARED_SECRET="$(docker exec bomi-backend printenv OPERATOR_SHARED_SECRET)"
test -n "$OPERATOR_SHARED_SECRET"

streamlit run app.py
```

기본 설정은 `127.0.0.1:8501`에만 바인딩된다. 운영자 PC에서 SSH 터널을 연다.

```bash
ssh -L 8501:127.0.0.1:8501 ubuntu@i15e102.p.ssafy.io
```

브라우저에서 `http://localhost:8501`을 연다. EC2 보안 그룹에 8501 포트를 공개하지
않는다.

## 안전 절차

1. 화면에서 Robot mode와 활성 Scenario를 확인한다.
2. 로봇 주변의 물리적 안전을 확인하고 `진행 중 내비게이션 취소`를 누른다.
3. Scenario가 `CANCELLED`, Robot mode가 `SAFE_STOP`으로 바뀌는지 확인한다.
4. Jetson/Nav2에서 Robot이 실제로 정지했는지 확인한다.
5. 별도의 안전 확인 후 `IDLE로 복구`를 누른다.

두 버튼을 한 번에 실행하지 않는다. MQTT `CANCEL` 발행과 실제 모터 정지 사이에는
시간 차이가 있을 수 있다.

## 테스트

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```
