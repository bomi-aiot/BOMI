# CLAUDE.md — Backend API 문서화 규칙 (필수)

이 규칙은 `backend/` 안에서 작업할 때 항상 적용됩니다. 새 API를 만들거나 계약을 바꾸는
모든 작업에 해당합니다. 전체 배경은 [`../docs/api/README.md`](../docs/api/README.md)에 있습니다.

## 1. 새 컨트롤러에는 `@Tag` 를 반드시 붙입니다

`@RestController` 를 추가하면 클래스에 `@Tag` 를 붙이고, **description 에 누가 호출하는지**
적습니다. 문장은 "…가 호출합니다." 로 끝냅니다.

```java
@RestController
@RequestMapping("/api/v1/robot/door-events")
@Tag(name = "Robot Door Event", description = "현관 이벤트 전달 — 로봇(ai_chat door_client)이 호출합니다.")
public class RobotDoorEventController { ... }
```

이 규칙은 `OpenApiDocumentationTest.everyControllerDeclaresATagNamingItsCaller` 가 강제합니다.
태그를 빠뜨리면 springdoc 이 클래스명으로 기본 태그를 만들어 주기 때문에 Swagger 화면은
멀쩡해 보이고, "이 API 를 누가 호출하는가"라는 정보만 조용히 사라집니다. 그래서 문서가
아니라 테스트로 막습니다.

## 2. 경로가 곧 채널입니다

Swagger 드롭다운은 `springdoc.group-configs` 의 `paths-to-match` 로 갈립니다. 새 엔드포인트를
만들 때 **호출 주체에 맞는 경로 접두어**를 고르면 그룹에 자동으로 들어갑니다.

| 호출 주체 | 경로 접두어 | 그룹 |
| --- | --- | --- |
| 로봇·AI (`ai_chat`) | `/api/v1/robot/**`, `/api/v1/seniors/**` | `bomi-robot` |
| 가디언웹 | `/api/v1/guardian/**`, `/api/v1/memories/**`, `/api/v1/care-records/**`, `/api/v1/confirmation-requests/**`, `/api/v1/elders/**` | `bomi-guardian` |

두 채널에 모두 해당하지 않는 새 채널이 생기면 `application.yml` 의 `group-configs` 에 그룹을
추가하고 `OpenApiDocumentationTest.channelGroupsContainOnlyTheirOwnPaths` 에 확인을 넣습니다.

**같은 테이블을 다루더라도 호출 주체가 다르면 컨트롤러를 나눕니다.** `fact_candidate` 를
로봇용 `/api/v1/robot/clarifications` 와 가디언웹용 `/api/v1/confirmation-requests` 로 나눈
것이 그 예입니다. 권한과 행위자가 다르기 때문입니다.

## 3. MQTT 를 바꾸면 세 파일을 함께 고칩니다

MQTT 는 REST 가 아니므로 Swagger 에 넣지 않습니다. OpenAPI 3.x 에는 토픽·QoS·발행자를
표현할 문법이 없고, 억지로 `paths` 에 넣으면 호출 가능한 REST 처럼 보여 오해를 만듭니다.

5개 시나리오의 토픽이나 메시지 필드를 바꾸면 **반드시 세 파일을 함께** 고칩니다.

1. `../docs/mqtt/시나리오 계약 v1.md` — 메시지 의미의 최종 기준
2. `src/main/resources/static/openapi/bomi-mqtt.asyncapi.yaml` — 기계가 읽는 스펙
3. `../docs/mqtt/토픽 규약.md` — 공통 토픽·봉투 규칙

`AsyncApiDocumentationTest`는 토픽 누락, 내부 참조, 핵심 메시지 예시 존재 여부를
검사합니다. 필드나 enum의 의미 변경은 세 파일을 함께 리뷰해야 합니다.

## 4. 정적 스펙을 추가하면 세 곳을 함께 고칩니다

`static/openapi/` 에 파일을 하나 추가하면 다음을 같이 바꿉니다. 하나라도 빠지면 배포에서
404 가 나거나 드롭다운에 나타나지 않습니다.

1. `src/main/resources/application.yml` — `springdoc.swagger-ui.urls`
2. `../infra/nginx/conf.d/bomi.conf` — 문서 `location` 정규식의 허용 목록
3. `../docs/api/README.md` — 도메인별 문서 위치 표와 스펙 목록

`group-configs` 로 만든 **그룹은 `swagger-ui.urls` 에 적지 않습니다.** springdoc 이
`display-name` 으로 이미 드롭다운에 넣으므로 또 적으면 항목이 두 번 뜹니다.

## 5. 파일명과 표시명

```text
<domain>-<service>.openapi.yaml    REST 계약
<domain>.asyncapi.yaml             메시지 계약
```

드롭다운 표시명에는 도메인 접두어를 붙입니다 — `[BE-Robot]`, `[BE-Guardian]`, `[BE-All]`,
`[AI-Vision]`, `[AI-Chat]`, `[MQTT]`.

구현체가 아직 없는 계약은 표시명 끝에 `(계약·미구현)` 을 붙이고 스펙 `info.description`
첫 문단에도 같은 사실을 적습니다. 그래야 지금 호출할 수 있는 API 로 오해되지 않습니다.

## 6. 뷰어에 외부 리소스를 쓰지 않습니다

운영 Nginx 의 CSP 는 `default-src 'self'; script-src 'self'` 입니다. CDN 스크립트·폰트·
스타일시트는 차단되므로 문서 페이지에 넣지 않습니다. `AsyncApiDocumentationTest` 가
뷰어 HTML 의 외부 URL 을 거부합니다.

## 7. 문서 변경 후 확인

```bash
./gradlew test --tests "com.ssafy.bomi.docs.*"
```

브라우저로 볼 때는 PostgreSQL 없이 뜨는 `docs` Profile 을 씁니다.

```bash
./gradlew bootRun --args='--spring.profiles.active=docs'
```

- `http://localhost:8080/swagger-ui.html` — REST
- `http://localhost:8080/asyncapi/mqtt/` — MQTT
- `http://localhost:8080/docs/` — 진입점
