# 아키텍처 장표 모음

> 팀 Miro 보드의 장표를 저장소로 가져온 것입니다. 원본 보드:
> https://miro.com/app/board/uXjVPMaJRWc=/
>
> **정본은 코드입니다.** 모든 장표는 2026-08-16에 `main` 코드와 전수 대조해 정정했습니다
> (시나리오 워치독 10분, waypoints 실측 좌표, SPEAK 발행 0건 등). 코드가 바뀌면 이 문서와
> Miro 보드를 함께 갱신하십시오.
>
> 읽는 순서: 전경 한 장(X) → 배포 토폴로지(A) → 기술 스택(H) → MQTT 배선(B) →
> 백엔드 내부(E) → ai_chat 내부(D) → 상태·안전(F) → 시나리오 4장(C1~C4) → 로컬 저장소(G)

## X. 시스템 전경 — 센서에서 모터까지 한 장

센서(파이) → 브로커 → 백엔드(EC2) → 젯슨(대화·비전·주행) → 하드웨어(Pico·모터)로 이어지는
전 구간입니다. 실선 화살표는 실제로 오가는 경로이고, 점선은 기본 설정에서 꺼져 있는 경로입니다.

```mermaid
flowchart LR
    classDef sensor fill:#f8d3af,stroke:#9b4a07
    classDef pi fill:#fff6b6,stroke:#af7e02
    classDef ec2 fill:#c6dcff,stroke:#305bab
    classDef jetson fill:#dbfaad,stroke:#608520
    classDef hw fill:#ffd8f4,stroke:#af3fb9
    classDef off fill:#ffc6c6,stroke:#bd0909
    classDef ext fill:#e7e7e7,stroke:#595959

    subgraph S1["1. 스마트홈 센서"]
        DHT["DHT11 온습도"]:::sensor
        DOOR["문열림 센서"]:::sensor
        PIR["PIR 모션"]:::sensor
    end

    subgraph S2["2. 라즈베리파이 5"]
        DHTM["dht11_main.py<br/>GPIO4 직접 읽기<br/>(translator 미경유)"]:::pi
        Z2M["Zigbee2MQTT"]:::pi
        TR["translator<br/>Zigbee 값 → 계약 이벤트"]:::pi
        LM["로컬 Mosquitto :1883<br/>bridge out 설정"]:::pi
    end

    subgraph S3["3. EC2 — Jenkins 자동 배포"]
        EM["Mosquitto :8883 TLS<br/>QoS 1 · retain=false"]:::ec2
        BE["Spring Boot 백엔드<br/>시나리오 오케스트레이션"]:::ec2
        PG[("PostgreSQL 17<br/>정본")]:::ec2
        QD[("Qdrant<br/>기본 비활성")]:::off
        FE["React 보호자 대시보드"]:::ec2
    end

    subgraph S4["4. 젯슨 — 수동 배포"]
        WW["ai_chat 웨이크워드 게이트<br/>openWakeWord 온디바이스"]:::jetson
        CONV["ai_chat 대화 그래프<br/>LangGraph"]:::jetson
        YOLO["ai_vision<br/>YOLO11n 사람 탐지"]:::jetson
        BT["ByteTrack 추적"]:::jetson
        BR["bridge<br/>MQTT ↔ Nav2"]:::jetson
        NAV["Nav2 · twist_mux<br/>/cmd_vel"]:::jetson
        VUB["vision_udp_bridge<br/>wake_search · person_follower"]:::jetson
        PD["pico_driver"]:::jetson
    end

    subgraph S5["5. 로봇 하드웨어"]
        PICO["RP2040 Pico<br/>워치독 300ms"]:::hw
        IMU["IMU"]:::hw
        MDD["MDD10A 모터드라이버"]:::hw
        MOT["모터 · 엔코더"]:::hw
    end

    SAAS["외부 SaaS<br/>RTZR STT · Gemini LLM · Typecast TTS"]:::ext

    DHT -->|"GPIO4"| DHTM
    DHTM -->|"MQTT"| LM
    DOOR -->|"Zigbee"| Z2M
    PIR -->|"Zigbee"| Z2M
    Z2M -->|"MQTT"| LM
    LM <-->|"구독·번역·발행"| TR
    LM ==>|"MQTT over TLS 브리지"| EM
    EM <-->|"이벤트 수신 · 명령 발행"| BE
    BE --> PG
    BE -.->|"기본 꺼짐"| QD
    FE -->|"REST 1초 폴링"| BE
    EM <-->|"START_CONVERSATION ↓<br/>대화·웨이크 이벤트 ↑"| WW
    EM <-->|"NAVIGATE·FOLLOW ↓<br/>결과 회신 ↑"| BR
    WW --> CONV
    CONV -->|"HTTPS"| SAAS
    CONV -->|"REST 기록·조회"| BE
    CONV -->|"UDP 5006 소리 방향"| VUB
    YOLO --> BT
    BT -->|"UDP 5005 사람 좌표"| VUB
    BR --> NAV
    VUB --> NAV
    NAV --> PD
    PD <-->|"시리얼 USB"| PICO
    IMU -->|"I2C"| PICO
    PICO -->|"PWM / DIR"| MDD
    MDD --> MOT
    MOT -->|"엔코더 펄스"| PICO
```

## A. 배포 토폴로지 — 기계와 프로세스

어느 기계에서 어떤 프로세스가 돌고, 무엇이 자동 배포이고 무엇이 수동인지입니다.
CI/CD가 배포하는 것은 EC2의 백엔드·프런트엔드·브로커뿐이고, 젯슨과 라즈베리파이는
`main`을 직접 checkout 해 수동 배포합니다.

```mermaid
flowchart TB
    classDef ec2 fill:#c6dcff,stroke:#305bab
    classDef fe fill:#dedaff,stroke:#6631d7
    classDef jetson fill:#dbfaad,stroke:#608520
    classDef pi fill:#f8d3af,stroke:#9b4a07
    classDef broker fill:#fff6b6,stroke:#af7e02
    classDef db fill:#e7e7e7,stroke:#595959
    classDef hw fill:#ffd8f4,stroke:#af3fb9
    classDef off fill:#ffc6c6,stroke:#bd0909

    subgraph EC2["EC2 i15e102.p.ssafy.io — 유일한 CI/CD 자동 배포"]
        NGINX["nginx<br/>/api/ 만 백엔드로<br/>그 외는 FE가 200+HTML"]:::ec2
        BE["Spring Boot 백엔드<br/>scenario·mqtt·conversation<br/>observation·occupancy"]:::ec2
        FE["React 19 대시보드<br/>REST 폴링만"]:::fe
        PG[("PostgreSQL 17<br/>정본 저장소")]:::db
        QD[("Qdrant<br/>기본 비활성<br/>QDRANT_HOST 빈 값")]:::off
    end

    BROKER["MQTT 브로커 :8883 TLS<br/>QoS 1 · retain=false"]:::broker

    subgraph JET["젯슨 — 수동 배포 · main 을 직접 checkout"]
        AICHAT["ai_chat<br/>웨이크워드·대화·TTS<br/>독립 venv"]:::jetson
        BRIDGE["bridge (ROS2)<br/>commands 토픽만 구독"]:::jetson
        VISION["ai_vision<br/>YOLO11n 사람 탐지<br/>독립 venv"]:::jetson
        CORE["core (ROS2)<br/>wake_search·person_follower<br/>vision_udp_bridge·pico_driver"]:::jetson
        NAV2["Nav2 + twist_mux<br/>waypoints 실측 좌표<br/>(재매핑하면 무효 —<br/>bomi_map.sh 가 갱신)"]:::jetson
    end

    subgraph PI["라즈베리파이 5 — 수동 배포"]
        DOOR["Zigbee2MQTT + translator<br/>문열림·모션"]:::pi
        DHT["dht11_main.py<br/>GPIO4 직결 · translator 미경유"]:::pi
    end

    MOTOR["RP2040 Pico + MDD10A<br/>워치독 300ms"]:::hw

    DOOR -->|"bomi/v1/iot/+/events"| BROKER
    DHT -->|"bomi/v1/iot/+/events"| BROKER
    BROKER <-->|"구독 4패턴 · 명령 발행"| BE
    BROKER -->|"NAVIGATE·FOLLOW_*·CANCEL"| BRIDGE
    BROKER -->|"START_CONVERSATION"| AICHAT
    AICHAT -->|"events 발행<br/>results·commands 엿듣기"| BROKER
    BRIDGE -->|"results 회신"| BROKER
    BRIDGE -->|"NavigateToPose 액션"| NAV2
    BRIDGE -->|"wake_search·person_follower 스위치"| CORE
    AICHAT -->|"UDP 5006 소리 각도"| CORE
    VISION -->|"UDP 5005 사람 좌표"| CORE
    CORE -->|"/cmd_vel → 시리얼"| MOTOR
    NAV2 -->|"twist_mux 경유"| CORE
    AICHAT -->|"REST /api/v1"| NGINX
    NGINX --> BE
    BE --> PG
    BE -.->|"기본 꺼짐"| QD
    FE -->|"REST 폴링 — WebSocket 없음"| NGINX
```

## H. 기술 스택 — 매니페스트 기준

각 라인이 실제 매니페스트(package.json·build.gradle·pyproject·requirements)에 선언한
것만 담았습니다. 붉은 상자는 팀이 이미 밟았던 함정입니다.

```mermaid
flowchart TB
    classDef fe fill:#dedaff,stroke:#6631d7
    classDef be fill:#c6dcff,stroke:#305bab
    classDef data fill:#e7e7e7,stroke:#595959
    classDef ai fill:#dbfaad,stroke:#608520
    classDef robo fill:#adf0c7,stroke:#087429
    classDef iotc fill:#f8d3af,stroke:#9b4a07
    classDef infra fill:#fff6b6,stroke:#af7e02
    classDef ext fill:#ffd8f4,stroke:#af3fb9
    classDef off fill:#ffe0e0,stroke:#c0392b
    classDef warn fill:#ffc6c6,stroke:#bd0909

    subgraph FE["Frontend — EC2 · 자동 배포"]
        FE1["React 19.2 · TypeScript 7.0"]:::fe
        FE2["Vite 8.1 빌드"]:::fe
        FE3["Three.js 0.185"]:::fe
        FE4["라우터·상태·테스트 라이브러리 없음<br/>네이티브 fetch · REST 폴링"]:::fe
    end

    subgraph BE["Backend — EC2 · 자동 배포"]
        BE1["Java 17 · Spring Boot 3.4.7"]:::be
        BE2["Spring Data JPA · Flyway"]:::be
        BE3["Spring Integration MQTT"]:::be
        BE4["springdoc-openapi 2.8"]:::be
        BE5["Micrometer Prometheus"]:::be
        BE6["JUnit 5 · Zonky 내장 PG"]:::be
        BE7["WebSocket 미사용<br/>STOMP·SSE 코드 0건"]:::warn
    end

    subgraph DATA["데이터 계층"]
        DB1["PostgreSQL 17<br/>정본 · 스키마는 Flyway"]:::data
        DB2["Qdrant v1.18.3<br/>기본 비활성<br/>QDRANT_HOST 빈 값"]:::off
        DB3["pgvector 미사용<br/>4096차원이 불가능한 값"]:::warn
    end

    subgraph AI["AI 대화 — 젯슨 · 수동 배포"]
        AI1["Python 3.10~3.12"]:::ai
        AI2["LangGraph 1.x<br/>SQLite 체크포인트"]:::ai
        AI3["openWakeWord + ONNX<br/>자체 학습 bomiya.onnx"]:::ai
        AI4["sounddevice · noisereduce"]:::ai
        AI5["APScheduler 배경 틱"]:::ai
        AI6["paho-mqtt 1.x 핀"]:::ai
    end

    subgraph EXT["외부 AI API"]
        EX1["Gemini 2.5 Flash-Lite<br/>로봇 대화는 상시 사용"]:::ext
        EX2["RTZR Sommers STT"]:::ext
        EX3["Typecast TTS ssfm-v30"]:::ext
        EX4["Upstage 임베딩 4096<br/>백엔드에서 기본 꺼짐"]:::off
        EX5["Gemini 요약 (백엔드)<br/>기본 꺼짐"]:::off
    end

    subgraph ROBO["Robotics — 젯슨 · 수동 배포"]
        RO1["Ubuntu 22.04 · ROS 2 Humble"]:::robo
        RO2["Nav2 · slam_toolbox"]:::robo
        RO3["YDLIDAR 드라이버 · rf2o"]:::robo
        RO4["robot_localization · twist_mux<br/>입력 5개 우선순위 중재"]:::robo
        RO5["YOLO11n + ByteTrack<br/>ultralytics 8.3 · OpenCV 4"]:::robo
        RO6["RP2040 Pico<br/>MicroPython + pyserial"]:::robo
        RO7["Gazebo 시뮬 · PySide6 표정"]:::robo
        RO8["paho-mqtt 2.x 핀"]:::robo
    end

    subgraph IOT["IoT — 라즈베리파이 5 · 수동 배포"]
        IO1["Python 3.12 · Docker Compose"]:::iotc
        IO2["Zigbee2MQTT · ZBDongle-P"]:::iotc
        IO3["Mosquitto 2 · TLS 브리지 out"]:::iotc
        IO4["DHT11 GPIO4 직결<br/>translator 미경유"]:::iotc
        IO5["systemd 부팅 자동 실행"]:::iotc
        IO6["paho-mqtt 2.x 핀"]:::iotc
    end

    subgraph INF["Infra · DevOps — EC2"]
        IN1["Docker Compose 3종"]:::infra
        IN2["Nginx 1.30 · TLS 종단"]:::infra
        IN3["Mosquitto 2.0.22 · 8883"]:::infra
        IN4["Jenkins 자체 호스팅<br/>be·fe·mqtt 만 자동 배포"]:::infra
        IN5["Certbot Let's Encrypt"]:::infra
        IN6["Streamlit 운영 도구 3종"]:::infra
        IN7["GitLab — 저장소·MR 만"]:::infra
    end

    PIN["paho-mqtt 핀 상이<br/>ai_chat 1.x ↔ robot·iot 2.x<br/>2.x 는 콜백 규약부터 다름"]:::warn

    FE -->|"REST 폴링"| BE
    BE -->|"JPA"| DATA
    BE -.->|"기본 꺼짐"| EXT
    AI -->|"상시 호출"| EXT
    AI --- PIN
    IOT --- PIN
    ROBO --- PIN
```

## B. MQTT 토픽 배선 — 코드가 기준

브로커를 지나는 토픽은 6개뿐입니다. 점선은 "엿듣기"(구독하지만 그 채널의 주인이 아님)이고,
아래 규칙 상자들은 어기면 **에러 응답 없이 조용히 폐기**되는 것들입니다.

```mermaid
flowchart LR
    classDef pi fill:#f8d3af,stroke:#9b4a07
    classDef topic fill:#fff6b6,stroke:#af7e02
    classDef be fill:#c6dcff,stroke:#305bab
    classDef robot fill:#dbfaad,stroke:#608520
    classDef rule fill:#ffc6c6,stroke:#bd0909
    classDef note fill:#e7e7e7,stroke:#595959
    classDef off fill:#ffe0e0,stroke:#c0392b

    PREFIX["토픽 접두어 bomi/v1/ 은 아래에서 생략<br/>브로커 경유는 전부 이 6개뿐"]:::note

    IOT["IoT 파이<br/>translator + dht11"]:::pi
    BEP["백엔드 발행"]:::be
    AIP["ai_chat 발행"]:::robot
    BRP["bridge 발행"]:::robot

    T1["iot/+/events<br/>DOOR_OPENED · DOOR_CLOSED<br/>MOTION_DETECTED<br/>AMBIENT_ENVIRONMENT_OBSERVED"]:::topic
    T2["robot/{id}/commands<br/>NAVIGATE · CANCEL<br/>FOLLOW_START · FOLLOW_STOP<br/>SPEAK — 발행 코드 0건 (enum 에만)"]:::topic
    T3["ai/{id}/commands<br/>START_CONVERSATION"]:::topic
    T4["robot/{id}/events<br/>WAKE_WORD_DETECTED<br/>CONVERSATION_STARTED · ENDED<br/>WALK_REQUESTED"]:::topic
    T5["robot/{id}/status<br/>메서드는 있으나<br/>운영 호출자 0건<br/>실제로는 발행 안 됨"]:::off
    T6["robot/{id}/results<br/>NAVIGATION_RESULT v1<br/>FOLLOW_RESULT ACK"]:::topic

    BEC["백엔드 구독 4패턴<br/>iot/+/events · robot/+/events<br/>robot/+/status · robot/+/results"]:::be
    BRC["bridge 구독<br/>commands 하나뿐"]:::robot
    AIC["ai_chat 구독<br/>ai/{id}/commands (QoS 1)<br/>iot/+/events (QoS 0)<br/>results·commands 엿듣기"]:::robot

    IOT --> T1 --> BEC
    T1 -.->|"현관 게이트 엿듣기"| AIC
    BEP --> T2 --> BRC
    T2 -.->|"NAVIGATE ENTRANCE<br/>출발 환호 엿듣기"| AIC
    BEP --> T3 --> AIC
    AIP --> T4 --> BEC
    BRP -.-> T5
    T5 -.-> BEC
    BRP --> T6 --> BEC
    T6 -.->|"ARRIVED 도착 엿듣기"| AIC

    subgraph RULES["공통 봉투 규칙 — 어기면 조용히 폐기, 에러 응답 없음"]
        R1["QoS 1 · retain=false<br/>QoS 0 폐기 · retained 폐기"]:::rule
        R2["필수: eventId ≤64자 · type<br/>occurredAt 오프셋 ISO8601<br/>payload · 최상위 robotId"]:::rule
        R3["상관 ID 는 최상위<br/>payload 안이면 거부"]:::rule
        R4["필드 화이트리스트 (4개 타입 한정)<br/>낯선 필드 1개 = 통째 거부"]:::rule
        R5["robotId = deviceId 공간<br/>bomi-AA001 형식<br/>REST UUID 와 혼용 금지"]:::rule
        R6["eventId dedup 은 인메모리<br/>InMemoryProcessedEventStore<br/>10분 TTL · 재시작하면 사라진다"]:::rule
    end

    subgraph MSG["주요 메시지 제약"]
        M1["START_CONVERSATION<br/>payload 4필드 전부 필수<br/>intent 3종만 허용<br/>expiresAt 실제 10초"]:::rule
        M2["NAVIGATION_RESULT v1<br/>SUCCEEDED → ARRIVED + null<br/>비성공 → NOT_ARRIVED + 사유"]:::rule
        M3["reasonCode 키는 항상 존재<br/>값 null 은 허용<br/>enum 은 코드 기준 7개"]:::rule
        M4["FOLLOW_RESULT<br/>STARTED·STOPPED = 접수 확인<br/>UNCHANGED = 시작 불가<br/>훅 실행보다 먼저 회신"]:::rule
        M5["CONVERSATION_STARTED<br/>상관 ID 3개 최상위 필수<br/>ENDED 는 commandId 없음"]:::rule
    end
```

## E. 백엔드 내부 — 모듈과 DB

MQTT 파서에서 오케스트레이터를 지나 DB까지, 백엔드 안의 실제 배선입니다.

```mermaid
flowchart LR
    classDef mod fill:#c6dcff,stroke:#305bab
    classDef db fill:#e7e7e7,stroke:#595959
    classDef warn fill:#ffc6c6,stroke:#bd0909
    classDef api fill:#dbfaad,stroke:#608520
    classDef off fill:#ffe0e0,stroke:#c0392b

    PARSER["MqttInboundMessageParser<br/>화이트리스트 검증<br/>QoS 1 아니면 폐기<br/>위반 시 무응답 거부"]:::warn
    DISP["MqttInboundDispatcher<br/>핸들러 12개로 fan-out<br/>eventId 중복은 인메모리 차단"]:::mod

    subgraph INB["인입 핸들러 (scenario.inbound)"]
        H1["DoorOpened · DoorClosed<br/>EntranceMotion"]:::mod
        H2["WakeWordDetected"]:::mod
        H3["NavigationResult<br/>FollowResult"]:::mod
        H4["ConversationStarted · Ended"]:::mod
        H5["WalkRequested"]:::mod
        H6["AmbientObserved<br/>RestStateChanged"]:::mod
    end

    subgraph ORCH["오케스트레이터 (scenario.application)"]
        WO["WakeWordCallOrchestrator<br/>FOLLOW_START 발행<br/>NAVIGATE 아님"]:::mod
        HO["HomecomingOrchestrator<br/>NAVIGATE ENTRANCE<br/>대화 후 beginFollowing 분기"]:::mod
        MO["MedicationReminderScheduler<br/>fixedDelay 60초<br/>창 = 예정−lead ~ 예정+grace"]:::mod
        WELL["WellnessCheckOrchestrator<br/>임계 이상이면 NAVIGATE<br/>scenarioEnabled 게이트"]:::mod
        WALK["WalkOrchestrator<br/>FOLLOW_START / FOLLOW_STOP<br/>산책 — 백엔드는 구현 완료"]:::mod
        ROUT["NavigationResultRouter<br/>FollowResultRouter<br/>scenarioType 별 분기"]:::mod
    end

    DIR["EntranceDirectionResolver<br/>기본 비활성<br/>direction-resolution-enabled=false<br/>→ DOOR_OPENED 가 직행"]:::off
    OBS["RobotObservationService<br/>temperatureC·humidityPercent<br/>키 없으면 조용히 제외"]:::warn
    GATE["MqttConversationGateway<br/>START_CONVERSATION 발행<br/>expiresAt = now + 10초"]:::mod

    subgraph POL["안전 정책"]
        GUARD["ScenarioRobotStartPolicy<br/>ScenarioStartGuard<br/>SAFE_STOP·중복 시나리오 차단"]:::warn
        WD["ScenarioTimeoutWatchdog 10분<br/>(SCENARIO_ACTIVE_TIMEOUT:10m<br/>시연용 단축, 원래 20분)<br/>AiConversationTimeoutWatchdog 5분<br/>WalkTimeoutWatchdog"]:::warn
    end

    subgraph RESTAPI["REST — 로봇에서 BE 로 단방향"]
        R1["conversation-context<br/>매 턴 · 1.5초 예산"]:::api
        R2["conversation-events<br/>턴당 2회 · SENIOR 먼저"]:::api
        R3["guardian-alerts<br/>outbox_flush 가 호출"]:::api
        R4["door-events<br/>실패해도 재시도 없음"]:::api
        R5["onboarding 3 · clarifications 2<br/>fact-candidates 2"]:::api
        R6["operator — mode-recoveries<br/>runtime-state · cancellations"]:::api
    end

    subgraph PGDB["PostgreSQL 17"]
        TW["로봇이 쓰는 표<br/>conversation·message<br/>care_record·occupancy_event<br/>onboarding·fact_candidate"]:::db
        TR["로봇은 읽기만<br/>memory·app_user·summary<br/>쓰기는 fact_candidate 경유"]:::db
        ST["scenario · robot<br/>mode = SAFE_STOP"]:::db
    end

    VEC["Qdrant + Upstage 임베딩<br/>둘 다 기본 꺼짐<br/>꺼지면 키워드 검색으로 폴백"]:::off
    LLM["Gemini 요약 생성<br/>bomi.llm.enabled 기본 false"]:::off

    PARSER --> DISP --> INB
    H1 -.->|"옵션 켤 때만"| DIR
    DIR --> HO
    H1 -->|"기본 경로"| HO
    H2 --> WO
    H3 --> ROUT
    ROUT --> WO
    ROUT --> HO
    ROUT --> WALK
    H4 --> HO
    H5 --> WALK
    H6 --> OBS --> WELL
    MO --> GATE
    HO --> GATE
    WELL --> GATE
    WO --- GUARD
    WALK --- WD
    ORCH --> ST
    RESTAPI --> TW
    R1 --> TR
    R1 -.-> VEC
    ST -.- LLM
```

## D. ai_chat 내부 — 스레드와 그래프

마이크는 한 스레드만 쥘 수 있어서, MQTT 수신·도착 감시·환호는 각자 스레드로 돌고
실제 대화는 전부 메인 루프의 LangGraph 파이프라인을 지납니다.

```mermaid
flowchart TB
    classDef entry fill:#adf0c7,stroke:#087429
    classDef node fill:#fff6b6,stroke:#af7e02
    classDef decision fill:#c6dcff,stroke:#305bab
    classDef store fill:#e7e7e7,stroke:#595959
    classDef warn fill:#ffc6c6,stroke:#bd0909
    classDef thread fill:#dedaff,stroke:#6631d7

    WAKE["wait_for_wake — 보미야 대기<br/>interrupt_check 1초 폴링<br/>실기 미검증 (V3 확인)"]:::entry
    SUB["AiCommandSubscriber<br/>paho 콜백 스레드<br/>파싱·dedup·만료 확인<br/>STARTED 즉시 발행"]:::thread
    QUEUE["backend_conversation_queue<br/>마이크는 한 스레드만"]:::store
    NAVW["NavigationArrivalWatcher<br/>results 엿듣기<br/>NAVIGATION_RESULT ARRIVED 만<br/>FOLLOW_RESULT 는 안 봄"]:::thread
    CHEER["EntranceCheerWatcher<br/>commands 엿듣기<br/>NAVIGATE ENTRANCE 출발 환호"]:::thread
    BEAM["BeamDirectionSampler<br/>마이크 배열 각도 주기 샘플<br/>3초 창 · 표본 2개 이상 합의"]:::thread

    ORDER["웨이크 직후 순서 (bootstrap)<br/>1 큐 우선 확인<br/>2 웨이크 게이트<br/>3 UDP 5006 소리 각도 발신<br/>4 WAKE_WORD_DETECTED 발행<br/>5 응답 한마디 → 대화"]:::node
    WAIT["이동 중 침묵은 옵트인<br/>FOLLOW 흐름엔 ARRIVED 없음<br/>→ 켜면 매번 45초 손해"]:::warn
    BCONV["_run_backend_conversation<br/>첫 문장 backend_command<br/>종료 사유 → ENDED outcome"]:::node
    CKPT["P1-b 오염 방어<br/>빈 명령의 이전 intent<br/>재사용 금지"]:::warn

    subgraph GRAPH["LangGraph 턴 파이프라인 — 시연 env 는 그래프 고정"]
        ING["note_interaction<br/>침묵시계 0 · 재실 HOME<br/>맞장구 · 말끊기 처리"]:::node
        TRI{"safety_triage<br/>none · confirm · T1"}:::decision
        CTX["context_read<br/>BE 문맥 1.5초 예산<br/>실패 시 캐시 폴백"]:::node
        CLS{"classify_intent<br/>문자열 검사 (LLM 아님)<br/>emotional 우선 · 기본 companion"}:::decision
        HDL["handle_*<br/>LLM 호출 턴당 1회"]:::node
        CONF["safety_confirm<br/>확인 질문 + 90초 마감"]:::node
        ESC["escalation<br/>outbox 에 T1 적재<br/>원문 미포함"]:::warn
        SHP["response_shaper<br/>모든 발화의 마지막 관문<br/>문장 단위 분할"]:::node
        MEM["memory_write<br/>SENIOR 먼저 ROBOT 다음<br/>실패해도 턴 안 막음"]:::node
        EMIT["emit — 즉시 반환<br/>재생은 백그라운드"]:::node
    end

    subgraph REST["백엔드 REST 클라이언트 — 전부 로봇에서 나가는 방향"]
        RC1["context · conversation<br/>door · guardian-alerts"]:::node
        RC2["onboarding 3 · clarifications 2<br/>fact-candidates 2"]:::node
        RC3["공통 인증 헤더<br/>BACKEND_SHARED_SECRET<br/>미설정이면 헤더 없음"]:::node
    end

    TICKS["배경 틱 (그래프 밖)<br/>silence · consent · outbox<br/>runtime_state 를 직접 읽음"]:::thread
    STORE["runtime.sqlite — 상태와 체크포인트<br/>outbox.sqlite — synchronous=FULL<br/>알림 무손실을 위해 파일 분리"]:::store

    WAKE --> ORDER
    ORDER --> ING
    ORDER --> BEAM
    ORDER -.- WAIT
    NAVW -.- WAIT
    WAKE -->|"큐에 항목"| BCONV
    SUB --> QUEUE --> BCONV
    BCONV --> ING
    BCONV -.- CKPT
    ING --> TRI
    TRI -->|"none"| CTX --> CLS --> HDL --> SHP
    TRI -->|"confirm"| CONF --> SHP
    TRI -->|"T1"| ESC --> SHP
    SHP --> MEM --> EMIT
    CTX --> RC1
    MEM --> RC1
    HDL --> RC2
    TICKS -.-> ESC
    ESC --> STORE
    TICKS --> STORE
```

## F. 상태·안전 — SAFE_STOP과 타임아웃

`COMPLETED`가 아닌 모든 시나리오 종료는 로봇을 `SAFE_STOP`으로 잠급니다.
자동 복구 경로는 없고, 해제 수단은 운영자 REST와 `reset-demo.sql` 둘뿐입니다.

```mermaid
flowchart TB
    classDef ok fill:#adf0c7,stroke:#087429
    classDef state fill:#fff6b6,stroke:#af7e02
    classDef bad fill:#ffc6c6,stroke:#bd0909
    classDef fix fill:#c6dcff,stroke:#305bab

    TRIG["트리거 5종<br/>웨이크 · 현관 · 복약 · 온습도 · 산책"]:::state
    NAVG["NAVIGATING"]:::state
    CONVG["CONVERSING"]:::state
    RET["RETURNING<br/>DEFAULT 복귀"]:::state
    DONE["scenario COMPLETED<br/>robot = IDLE"]:::ok
    FAILS["FAILED · CANCELLED<br/>TIMED_OUT"]:::bad
    SAFE["robot = SAFE_STOP<br/>모든 이동 시나리오 차단<br/>MQTT 로는 못 푼다"]:::bad
    STUCK["NAVIGATING 잔류 시<br/>ACTIVE_SCENARIO_EXISTS"]:::bad
    OPREST["운영자 REST<br/>POST /api/v1/operator/robots<br/>/{deviceId}/mode-recoveries<br/>감사 로그 남김"]:::fix
    RESET["reset-demo.sql<br/>리허설 사이마다 실행"]:::fix

    TRIG --> NAVG
    NAVG -->|"보미야·산책: FOLLOW ACK<br>즉시 종결"| DONE
    NAVG -->|"ARRIVED"| CONVG
    CONVG -->|"CONVERSATION_ENDED"| RET
    RET -->|"ARRIVED"| DONE
    NAVG -->|"실패·만료·워치독"| FAILS
    CONVG -->|"5분 초과"| FAILS
    FAILS --> SAFE
    NAVG -.-> STUCK
    SAFE --> OPREST
    SAFE --> RESET
    STUCK --> RESET

    subgraph TO["타임아웃 — 로봇의 데드라인"]
        TO1["NAVIGATE·FOLLOW TTL 2분<br/>만료 → COMMAND_EXPIRED"]:::state
        TO2["CONVERSATION_STARTED 10초<br/>계약 v1.1.0 에 반영 완료"]:::state
        TO3["대화 최대 5분<br/>AiConversationTimeoutWatchdog"]:::state
        TO4["시나리오 전체 10분<br/>SCENARIO_ACTIVE_TIMEOUT:10m<br/>시연용 단축 (원래 20분)<br/>ScenarioTimeoutWatchdog → TIMED_OUT"]:::state
        TO5["FOLLOW ACK 10초<br/>탐색보다 짧다<br/>→ 훅보다 먼저 회신이 규칙"]:::bad
        TO6["WalkTimeoutWatchdog<br/>FOLLOW_STOP 재발행 후 SAFE_STOP"]:::state
    end

    subgraph GATE["시작을 막는 것들"]
        G1["ScenarioRobotStartPolicy<br/>SAFE_STOP 이면 시작 거부"]:::bad
        G2["ScenarioStartGuard<br/>중복 시나리오 차단"]:::bad
        G3["eventId dedup 인메모리<br/>재시작하면 사라진다<br/>DB inbox 미구현"]:::bad
    end

    subgraph PHY["물리 안전"]
        P1["받침대 검증 전 모터 OFF<br/>바퀴 띄우고 ±0.03m/s 부터"]:::bad
        P2["0.5초 내 미정지 = 중단<br/>Pico 워치독 300ms"]:::bad
        P3["robotId당 소비자 1개<br/>bridge+robot-sim 동시 금지"]:::bad
        P4["실브로커에 publish_event<br/>이동 시나리오 시작 금지"]:::bad
        P5["person_follower LiDAR 게이팅<br/>정지 0.5m · 재개 1.0m · 비상 0.3m"]:::bad
    end
```

## C1. 보미야 호출 — FOLLOW_START 방식

고정 좌표로 이동하는 시나리오가 아닙니다. 백엔드는 `FOLLOW_START`를 내리고 즉시 종결하며,
회전 탐색과 접근은 전부 로봇 내부에서 — 그것도 킬 스위치를 켠 경우에만 — 일어납니다.

```mermaid
sequenceDiagram
    autonumber
    participant S as 어르신
    participant A as ai_chat
    participant C as core·vision
    participant B as 백엔드
    participant R as bridge

    S->>A: 보미야
    Note over A: 큐 우선 확인 → 웨이크 게이트
    A->>C: UDP 5006 — 소리 각도 힌트
    Note over A,C: MQTT 발행보다 먼저 나간다<br/>SearchSignalSender.send_wake()<br/>빔포밍 표본 합의 시에만 각도 포함
    A->>B: WAKE_WORD_DETECTED
    Note over B: eventId 영수증 dedup (인메모리)<br/>ScenarioStartPolicy 입장 판정<br/>SAFE_STOP·중복이면 조용히 차단
    B->>R: FOLLOW_START (TTL 2분, payload 빈 객체)
    Note over B,R: NAVIGATE 아님 — 로봇이<br/>스스로 찾아가는 방식
    R-->>B: FOLLOW_RESULT SUCCEEDED / STARTED
    Note over R: 훅 실행보다 먼저 회신한다<br/>ACK 데드라인 10초가<br/>탐색 시간보다 짧기 때문
    Note over B: scenario COMPLETED · robot IDLE<br/>탐색 결과는 보고받지 않음
    alt search_enabled = true 인 경우에만
        R->>C: /wake_search/start ← Bool(True)
        Note over C: 각도로 회전 (없으면 한 바퀴)<br/>vision UDP 5005 로 사람 발견<br/>→ /person_following/enable<br/>전부 로봇 내부, 백엔드 무관
    else 기본 구성 (search_enabled = false)
        Note over R: 훅이 None → 회전 탐색 없음<br/>FAILED / UNCHANGED 로 회신
    end
    A-->>S: 네, 말씀하세요
    A->>S: 본 대화 (LangGraph)
    Note over A: 이동 중 침묵 대기는 꺼 둠<br/>FOLLOW 흐름엔 ARRIVED 가 없다
```

## C2. 현관 인사

문 열림 이벤트 하나로 시작합니다. 방향 판정은 기본 꺼짐이라, 기본 구성에서는
`DOOR_OPENED`가 곧바로 귀가 시나리오를 엽니다.

```mermaid
sequenceDiagram
    autonumber
    participant D as 현관 센서
    participant B as 백엔드
    participant R as bridge
    participant A as ai_chat
    participant S as 어르신

    D->>B: DOOR_OPENED
    Note over B: 기본 설정에서는 방향판정을 건너뛰고<br/>DoorOpenedHandler 가 곧바로 startHomecoming<br/>direction-resolution-enabled 기본값 false
    opt 방향판정을 켠 경우에만
        D->>B: MOTION_DETECTED
        Note over B: EntranceDirectionResolver<br/>문열림 → 모션 순서 = 귀가 IN<br/>도착 시각 기준 (파이 RTC 불신)
    end
    B->>R: NAVIGATE ENTRANCE (TTL 2분)
    A--)A: commands 엿듣기 → 출발 환호
    Note over R: status 토픽은 실제로 발행되지 않음<br/>진행 상황 보고 없이 결과만 온다
    R-->>B: NAVIGATION_RESULT ARRIVED
    B->>A: START_CONVERSATION<br/>HOMECOMING_GREETING
    A-->>B: CONVERSATION_STARTED (10초 내)
    A->>S: 인사 1왕복 이상 (최대 5분)
    S-->>A: 응답
    A-->>B: CONVERSATION_ENDED outcome
    alt reasonCode 가 HOMECOMING_FOLLOW_COMPLETED 가 아니면
        B->>R: FOLLOW_START (beginFollowing)
        R-->>B: FOLLOW_RESULT STARTED
        Note over B,R: 인사 뒤 어르신을 따라가는 분기
    else 추종까지 끝난 경우
        B->>R: NAVIGATE DEFAULT
        R-->>B: ARRIVED
    end
    Note over B: scenario COMPLETED · robot IDLE<br/>COMPLETED 아니면 SAFE_STOP
```

## C3. 복약 알림

로봇이 시계를 보는 것이 아니라, 백엔드 스케줄러가 1분마다 복약 창을 검사해
시나리오를 엽니다.

```mermaid
sequenceDiagram
    autonumber
    participant M as MedicationReminderScheduler
    participant B as 백엔드
    participant R as bridge
    participant A as ai_chat
    participant S as 어르신

    Note over M: @Scheduled(fixedDelay = 60_000)<br/>창 = 예정−reminderLeadMinutes<br/>~ 예정+graceMinutes (설정값)<br/>시연: −5분에 care_record 슬롯 시드
    M->>B: 창 안 tick → 시나리오 시작
    Note over B: ScenarioStartPolicy 입장 판정<br/>SAFE_STOP·중복이면 조용히 침묵
    B->>R: NAVIGATE LIVING_ROOM (TTL 2분)
    R-->>B: NAVIGATION_RESULT ARRIVED
    B->>A: START_CONVERSATION<br/>MEDICATION_REMINDER
    A-->>B: CONVERSATION_STARTED (10초 내)
    A->>S: 약 드실 시간이에요
    S-->>A: 먹었어
    Note over A: handle_schedule 이 completed_slot 기록<br/>부정을 먼저 검사한다 — 안 먹었어 안에도<br/>먹었 이 들어 있어서 순서가 틀리면<br/>약을 거른 채 알림이 사라진다
    A-->>B: CONVERSATION_ENDED COMPLETED
    B->>R: NAVIGATE DEFAULT
    R-->>B: ARRIVED
    Note over B: scenario COMPLETED · robot IDLE
```

## C4. 온습도 안부

DHT11이 30초마다 읽어 올리고, 백엔드가 임계(30.0℃ 또는 80.0% **이상**)를 판정합니다.

```mermaid
sequenceDiagram
    autonumber
    participant D as dht11_main.py
    participant P as 파이 Mosquitto
    participant B as 백엔드
    participant R as bridge
    participant A as ai_chat
    participant S as 어르신

    Note over D: GPIO4 직결 · 30초 주기 폴링<br/>translator 를 거치지 않고 직접 발행<br/>0~50도 / 20~90%RH 밖이면 미발행<br/>시연: publish_event.py ambient --temp 31
    D->>P: AMBIENT_ENVIRONMENT_OBSERVED
    P->>B: bridge out — TLS :8883
    Note over D,B: 키는 temperatureC · humidityPercent<br/>sourceId = ambient-sensor-01<br/>둘 중 하나라도 틀리면 조용히 폐기
    Note over B: RobotObservationService 기록 후<br/>WellnessCheckOrchestrator 호출<br/>임계 30.0도 이상 또는 80.0% 이상<br/>scenarioEnabled 게이트도 통과해야 함
    B->>R: NAVIGATE LIVING_ROOM (TTL 2분)
    R-->>B: NAVIGATION_RESULT ARRIVED
    B->>A: START_CONVERSATION<br/>WELLNESS_CHECK
    A-->>B: CONVERSATION_STARTED (10초 내)
    A->>S: 온습도 안부 대화
    S-->>A: 응답
    A-->>B: CONVERSATION_ENDED COMPLETED
    B->>R: NAVIGATE DEFAULT
    R-->>B: ARRIVED
    Note over B: scenario COMPLETED · robot IDLE
```

## G. 로봇 로컬 저장소 — 두 개의 SQLite

같은 SQLite인데 파일이 둘인 이유: 보호자 알림(outbox)만은 전원이 끊겨도 잃으면
안 되기 때문입니다.

```mermaid
flowchart TB
    classDef file fill:#dedaff,stroke:#6631d7
    classDef tbl fill:#fff6b6,stroke:#af7e02
    classDef warn fill:#ffc6c6,stroke:#bd0909
    classDef note fill:#c6dcff,stroke:#305bab

    subgraph RT["runtime.sqlite — localstore/schema.py"]
        RS["runtime_state<br/>재실 · 침묵 사다리<br/>안전 확인 마감"]:::tbl
        SP["speech_proposal<br/>발화 제안 큐<br/>P1-a dispatcher 미배선"]:::warn
        CC["context_cache<br/>BE 문맥 읽기 캐시"]:::tbl
        CS["completed_slot<br/>약 먹었어 완료 기록"]:::tbl
        ES["emotional_signal<br/>정서 누적 · 원문 없음"]:::tbl
        CR["consent_request<br/>T3 동의 상태"]:::tbl
        DA["door_alert<br/>현관 알림 dedup"]:::tbl
        CA["cached_audio<br/>캐시 음성 목록"]:::tbl
        SPH["spoken_phrasing<br/>표현 반복 방지"]:::tbl
        EJ["extraction_job<br/>기억 추출 작업"]:::tbl
        FC["fact_cancel_request<br/>사실 취소 요청"]:::tbl
        CP["LangGraph 체크포인트<br/>별도 파일 아님<br/>P1-c ctx 무기한 누적"]:::warn
    end

    subgraph OB["outbox.sqlite — 파일 분리: 알림 무손실"]
        OBT["outbox<br/>보호자 알림 T1·T2·T3<br/>T1 은 무제한 재시도"]:::tbl
    end

    TRAP["이중 저장소 함정<br/>그래프 노드 → 체크포인트<br/>배경 감시 → runtime_state<br/>새 노드의 첫 질문:<br/>감시가 이 값을 읽는가"]:::note

    RS -.- TRAP
    CP -.- TRAP
```
