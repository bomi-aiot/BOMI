# BOMI Backend

Java 17 / Spring Boot / Gradle 기반 중앙 백엔드입니다.

1. 루트 `.env.example`을 `.env`로 복사하고 값을 설정합니다.
2. 루트에서 `docker compose up -d`로 MySQL과 Mosquitto를 시작합니다.
3. 이 디렉터리에서 `./gradlew bootRun`(Windows: `gradlew.bat bootRun`)을 실행합니다.
4. `GET http://localhost:8080/api/health`로 상태를 확인합니다.

MQTT 라이브러리와 접속 환경변수의 기반만 포함하며 실제 구독·발행 흐름은 후속 구현 대상입니다.
