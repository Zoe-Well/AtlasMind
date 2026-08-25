"""Python 3.14 and planned dependency compatibility gate."""

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from atlasmind.settings import Settings


@pytest.mark.contract
def test_python_runtime_is_314_or_newer() -> None:
    assert sys.version_info >= (3, 14)


@pytest.mark.contract
@pytest.mark.parametrize(
    "module",
    [
        "alembic",
        "asyncpg",
        "bs4",
        "boto3",
        "deepeval",
        "fastapi",
        "langgraph",
        "neo4j",
        "neo4j_graphrag",
        "opentelemetry",
        "pgvector",
        "pypdf",
        "sqlalchemy",
    ],
)
def test_planned_dependency_imports_on_python_314(module: str) -> None:
    assert importlib.import_module(module) is not None


@pytest.mark.contract
def test_settings_reject_missing_secrets(isolated_atlasmind_environment: None) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.contract
def test_compose_and_collector_configuration_exist() -> None:
    root = Path(__file__).parents[2]
    assert (root / "compose.yaml").is_file()
    assert (root / ".specify" / "otel-collector.local.yaml").is_file()
