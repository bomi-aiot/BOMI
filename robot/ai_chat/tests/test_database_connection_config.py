"""설정에 따른 direct/SSH 데이터베이스 연결 분기 테스트."""

from unittest.mock import Mock

from bomi_ai_chat.db import medical_repository


def test_direct_mode_uses_database_url(monkeypatch, settings_factory):
    settings = settings_factory(
        DB_CONNECTION_MODE="direct",
        DATABASE_URL="postgresql://user:password@db:5432/bomi",
    )
    connection = object()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(medical_repository, "get_settings", lambda: settings)
    monkeypatch.setattr(medical_repository.psycopg2, "connect", connect)

    assert medical_repository._get_conn() is connection
    connect.assert_called_once_with(
        "postgresql://user:password@db:5432/bomi",
        client_encoding="utf-8",
    )


def test_direct_mode_uses_individual_database_values(
    monkeypatch,
    settings_factory,
):
    settings = settings_factory(
        DB_CONNECTION_MODE="direct",
        DB_HOST="database.internal",
        DB_PORT="6432",
        DB_NAME="bomi",
        DB_USER="app",
        DB_PASSWORD="secret",
    )
    connection = object()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(medical_repository, "get_settings", lambda: settings)
    monkeypatch.setattr(medical_repository.psycopg2, "connect", connect)

    assert medical_repository._get_conn() is connection
    connect.assert_called_once_with(
        host="database.internal",
        port=6432,
        dbname="bomi",
        user="app",
        password="secret",
        client_encoding="utf-8",
    )


def test_ssh_mode_uses_forwarded_local_port(monkeypatch, settings_factory):
    settings = settings_factory(
        DB_NAME="bomi",
        DB_USER="app",
        DB_PASSWORD="secret",
        EC2_HOST="ec2.internal",
        SSH_KEY_PATH="keys/ec2.pem",
    )
    connection = object()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(medical_repository, "get_settings", lambda: settings)
    monkeypatch.setattr(medical_repository, "get_local_port", lambda: 6543)
    monkeypatch.setattr(medical_repository.psycopg2, "connect", connect)

    assert medical_repository._get_conn() is connection
    connect.assert_called_once_with(
        host="localhost",
        port=6543,
        dbname="bomi",
        user="app",
        password="secret",
        client_encoding="utf-8",
    )
