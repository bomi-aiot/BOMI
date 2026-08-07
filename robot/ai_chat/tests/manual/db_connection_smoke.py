"""선택한 direct/SSH 모드로 의료 DB 연결만 확인한다."""


def main() -> None:
    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.db.medical_repository import _get_conn

    settings = Settings.from_env()
    settings.validate_database()

    connection = _get_conn()
    try:
        print("DB 연결 성공!")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
