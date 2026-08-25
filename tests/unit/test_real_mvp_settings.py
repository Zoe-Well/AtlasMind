"""Startup gates for the persistent local MVP."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlasmind.settings import Settings

pytestmark = pytest.mark.usefixtures("isolated_atlasmind_environment")


def configured(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "environment": "development",
        "auth_mode": "local",
        "database_url": "postgresql+asyncpg://user:password@localhost:5432/atlasmind",
        "object_store_endpoint": "http://localhost:9000",
        "object_store_access_key": "local-access",
        "object_store_secret_key": "local-secret",
        "model_base_url": "http://localhost:11434/v1",
        "model_api_key": "local-model",
        "chat_model": "chat-model",
        "embedding_model": "embedding-model",
        "neo4j_password": "neo4j-local",
    }
    values.update(overrides)
    return values


def test_legacy_model_connection_is_used_for_both_capabilities() -> None:
    settings = Settings(_env_file=None, **configured())

    assert settings.resolved_chat_base_url == "http://localhost:11434/v1"
    assert settings.resolved_chat_api_key == "local-model"
    assert settings.resolved_embedding_base_url == "http://localhost:11434/v1"
    assert settings.resolved_embedding_api_key == "local-model"


def test_dedicated_chat_and_embedding_connections_work_without_legacy_values() -> None:
    values = configured(
        chat_base_url="https://api.deepseek.com",
        chat_api_key="deepseek-secret",
        embedding_base_url="http://localhost:11434/v1",
        embedding_api_key="ollama-local",
    )
    values.pop("model_base_url")
    values.pop("model_api_key")

    settings = Settings(_env_file=None, **values)

    assert settings.resolved_chat_base_url == "https://api.deepseek.com/"
    assert settings.resolved_chat_api_key == "deepseek-secret"
    assert settings.resolved_embedding_base_url == "http://localhost:11434/v1"
    assert settings.resolved_embedding_api_key == "ollama-local"


def test_partial_dedicated_connection_disables_only_that_capability() -> None:
    settings = Settings(
        _env_file=None,
        **configured(chat_base_url="https://api.deepseek.com"),
    )

    assert settings.chat_connection_configured is False
    assert settings.embedding_connection_configured is True
    assert settings.missing_model_capabilities == ("CHAT",)


def test_local_authentication_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="local authentication is forbidden"):
        Settings(
            _env_file=None,
            **configured(
                environment="production",
                otel_exporter_otlp_endpoint="http://localhost:4317",
            )
        )


def test_missing_model_configuration_is_reported_without_blocking_startup() -> None:
    values = configured(chat_model="", embedding_model="")
    values.pop("model_base_url")
    values.pop("model_api_key")

    settings = Settings(_env_file=None, **values)

    assert settings.missing_model_capabilities == ("CHAT", "EMBEDDING")
