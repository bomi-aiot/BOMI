"""RTZR 인증 토큰 발급 응답을 직접 확인한다."""


def main() -> None:
    import requests

    from bomi_ai_chat.config import Settings

    settings = Settings.from_env()
    if not settings.rtzr_client_id or not settings.rtzr_client_secret:
        raise SystemExit("RTZR_CLIENT_ID와 RTZR_CLIENT_SECRET이 필요합니다.")

    response = requests.post(
        "https://openapi.vito.ai/v1/authenticate",
        data={
            "client_id": settings.rtzr_client_id,
            "client_secret": settings.rtzr_client_secret,
        },
        timeout=15,
    )
    response.raise_for_status()
    print(response.status_code)
    print(response.json())


if __name__ == "__main__":
    main()
