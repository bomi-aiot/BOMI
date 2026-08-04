"""네 백엔드 클라이언트가 공유하는 인증 헤더 배선 (S15P11E102-307).

requests.Session 이 처음이라면
    requests.Session 은 커넥션을 재사용하는 객체이고, `session.headers` 에 넣은
    값은 그 세션으로 나가는 모든 요청에 자동으로 실린다. 지금까지 이 저장소의
    네 클라이언트(context/contract/conversation/door)는 세션을 아예 만들지 않고
    `requests` 모듈 자체를 기본값으로 썼다(`session or requests`) — 모듈에도
    `request()` 함수가 있어 호출 코드가 똑같이 동작하기 때문이다. 그래서 지금까지
    헤더를 실을 '세션'이 애초에 없었다.

왜 모듈 하나로 모았는가
    백엔드(be-develop, S15P11E102-307)에 `/api/v1/robot/**` 와 `/api/v1/seniors/**`
    를 지키는 서블릿 필터가 생긴다 — 공유 시크릿 헤더가 없거나 틀리면 401.
    네 클라이언트가 각자 헤더를 실으면 이름 오타나 갱신 누락이 생길 자리가 넷이
    된다. 여기 한 곳에서만 얹고, 클라이언트들은 세션을 받아 쓰기만 한다.
    (CLAUDE.md §20: backend_client/ 는 서버와 대화하는 유일한 통로다.)

참고
    CLAUDE.md §5 (API 이음새), §26 (env 가 실제로 프로세스에 도달했는지 확인)
    S15P11E102-307 (백엔드 측 필터, be-develop 브랜치)
"""

from __future__ import annotations

import requests

from bomi_ai_chat.config import Settings, get_settings

# 백엔드 필터가 검사하는 헤더 이름. be-develop 쪽 서블릿 필터와 합의된 이름이므로
# 바꾸려면 로봇과 백엔드를 같은 배포에서 함께 바꿔야 한다.
SHARED_SECRET_HEADER = "X-Robot-Shared-Secret"


def build_backend_session(settings: Settings | None = None) -> requests.Session:
    """공유 시크릿 헤더를 얹은 requests.Session 을 새로 만든다.

    무엇을 하는가
        settings.backend_shared_secret 이 설정돼 있으면 SHARED_SECRET_HEADER 로
        세션에 얹는다. 값이 비어 있으면(개발 환경 기본값) 헤더를 아예 달지 않는다 —
        백엔드도 시크릿이 없으면 헤더 검사를 건너뛰므로, 둘 다 "미설정"으로 맞아
        떨어진다.

    누가 호출하는가
        네 클라이언트(BackendContextClient, _ContractClient, BackendConversationClient,
        BackendDoorClient)의 __init__ 이 명시적 session 을 받지 않았을 때만.

    주의사항
        호출할 때마다 새 Session 을 만든다. 각 클라이언트가 자기 __init__ 에서
        한 번만 부르므로 커넥션 재사용 이점은 그대로 남는다 — 세션 하나를
        여러 클라이언트가 공유하는 것이 아니라, '헤더를 얹는 방법'을 공유한다.
    """
    settings = settings or get_settings()
    session = requests.Session()
    if settings.backend_shared_secret:
        session.headers[SHARED_SECRET_HEADER] = settings.backend_shared_secret
    return session
