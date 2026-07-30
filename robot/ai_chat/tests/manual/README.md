# 수동 연동 점검

이 디렉터리의 스크립트는 실제 자격증명, 네트워크, 데이터베이스,
마이크 또는 스피커를 사용한다. 기본 `pytest` 실행에서는 의도적으로
제외된다.

먼저 프로젝트를 설치한다.

```powershell
python -m pip install -e ".[dev]"
```

`robot/ai_chat`에서 필요한 점검만 하나씩 실행한다.

```powershell
python tests/manual/audio_smoke.py
python tests/manual/stt_smoke.py
python tests/manual/tts_smoke.py
python tests/manual/weather_smoke.py
python tests/manual/llm_smoke.py
python tests/manual/db_connection_smoke.py
python tests/manual/ec2_query_smoke.py
python tests/manual/medical_apis_smoke.py
python tests/manual/medical_flow_smoke.py
python tests/manual/rtzr_token_smoke.py
```

각 스크립트는 첫 외부 동작 전에 필수 설정을 확인한다. 하드웨어 점검은
운영자가 지켜보는 상태에서 실행하고, 실행하지 않은 점검은 통과로 기록하지
않는다.
