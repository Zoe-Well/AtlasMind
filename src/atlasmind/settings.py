"""Validated process configuration with explicit secret boundaries."""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProcessRole(StrEnum):
    API = "api"
    INGESTION = "ingestion"
    AGENT = "agent"
    EVALUATION = "evaluation"


class AuthMode(StrEnum):
    LOCAL = "local"
    OIDC = "oidc"


class Settings(BaseSettings):
    """Runtime settings loaded from environment only; secrets never use defaults."""

    model_config = SettingsConfigDict(
        env_prefix="ATLASMIND_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    process_role: ProcessRole = ProcessRole.API
    auth_mode: AuthMode = AuthMode.LOCAL
    database_url: SecretStr
    object_store_endpoint: AnyHttpUrl
    object_store_bucket: str = "atlasmind"
    object_store_access_key: SecretStr
    object_store_secret_key: SecretStr
    oidc_issuer: AnyHttpUrl | None = None
    oidc_audience: str | None = None
    model_base_url: AnyHttpUrl | None = None
    model_api_key: SecretStr | None = None
    chat_base_url: AnyHttpUrl | None = None
    chat_api_key: SecretStr | None = None
    embedding_base_url: AnyHttpUrl | None = None
    embedding_api_key: SecretStr | None = None
    chat_model: str | None = None
    chat_thinking_enabled: bool | None = None
    embedding_model: str | None = None
    embedding_revision: str = "1"
    retrieval_expand_neighbors: bool = False
    service_rerank_enabled: bool = False
    model_timeout_seconds: float = Field(default=60, gt=0, le=300)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr
    ingestion_poll_seconds: float = Field(default=1, gt=0, le=60)
    otel_exporter_otlp_endpoint: AnyHttpUrl | None = None
    authorization_cache_ttl_seconds: int = Field(default=30, ge=0, le=300)
    max_query_characters: int = Field(default=16_000, ge=1, le=64_000)
    service_jwt_secret: SecretStr | None = None
    service_profile: Literal["customer_service", "hq"] = "customer_service"
    service_scope_id: str = "00000000-0000-4000-8000-000000000030"
    local_scope_id: str = "00000000-0000-4000-8000-000000000010"
    service_management_enabled: bool = False

    @field_validator("local_scope_id", "service_scope_id")
    @classmethod
    def canonical_scope_id(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator(
        "chat_thinking_enabled",
        "model_base_url",
        "model_api_key",
        "chat_base_url",
        "chat_api_key",
        "embedding_base_url",
        "embedding_api_key",
        "chat_model",
        "embedding_model",
        mode="before",
    )
    @classmethod
    def empty_model_connection_value_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, SecretStr) and not value.get_secret_value().strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_runtime_boundaries(self) -> Settings:
        if self.service_management_enabled and self.local_scope_id == self.service_scope_id:
            raise ValueError("service knowledge must have a dedicated scope")
        if self.environment == "production" and self.otel_exporter_otlp_endpoint is None:
            raise ValueError("production requires an OTLP endpoint")
        if self.environment == "production" and self.auth_mode is AuthMode.LOCAL:
            raise ValueError("local authentication is forbidden in production")
        if self.auth_mode is AuthMode.OIDC and not (self.oidc_issuer and self.oidc_audience):
            raise ValueError("OIDC mode requires issuer and audience")
        return self

    @property
    def chat_connection_configured(self) -> bool:
        return self._chat_connection() is not None

    @property
    def embedding_connection_configured(self) -> bool:
        return self._embedding_connection() is not None

    @property
    def missing_model_capabilities(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.chat_connection_configured:
            missing.append("CHAT")
        if not self.embedding_connection_configured:
            missing.append("EMBEDDING")
        return tuple(missing)

    def _chat_connection(self) -> tuple[AnyHttpUrl, SecretStr, str] | None:
        if self.chat_base_url is not None or self.chat_api_key is not None:
            if self.chat_base_url and self.chat_api_key and self.chat_model:
                return self.chat_base_url, self.chat_api_key, self.chat_model
            return None
        if self.model_base_url and self.model_api_key and self.chat_model:
            return self.model_base_url, self.model_api_key, self.chat_model
        return None

    def _embedding_connection(self) -> tuple[AnyHttpUrl, SecretStr, str] | None:
        if self.embedding_base_url is not None or self.embedding_api_key is not None:
            if self.embedding_base_url and self.embedding_api_key and self.embedding_model:
                return self.embedding_base_url, self.embedding_api_key, self.embedding_model
            return None
        if self.model_base_url and self.model_api_key and self.embedding_model:
            return self.model_base_url, self.model_api_key, self.embedding_model
        return None

    @property
    def resolved_chat_base_url(self) -> str:
        connection = self._chat_connection()
        if connection is None:
            raise RuntimeError("chat model endpoint is not configured")
        return str(connection[0])

    @property
    def resolved_chat_api_key(self) -> str:
        connection = self._chat_connection()
        if connection is None:
            raise RuntimeError("chat model API key is not configured")
        return connection[1].get_secret_value()

    @property
    def resolved_chat_model(self) -> str:
        connection = self._chat_connection()
        if connection is None:
            raise RuntimeError("chat model is not configured")
        return connection[2]

    @property
    def resolved_embedding_base_url(self) -> str:
        connection = self._embedding_connection()
        if connection is None:
            raise RuntimeError("embedding model endpoint is not configured")
        return str(connection[0])

    @property
    def resolved_embedding_api_key(self) -> str:
        connection = self._embedding_connection()
        if connection is None:
            raise RuntimeError("embedding model API key is not configured")
        return connection[1].get_secret_value()

    @property
    def resolved_embedding_model(self) -> str:
        connection = self._embedding_connection()
        if connection is None:
            raise RuntimeError("embedding model is not configured")
        return connection[2]


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
