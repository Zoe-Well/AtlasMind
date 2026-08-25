"""Shared pytest fixtures for deterministic local and CI execution."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def isolated_atlasmind_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove runtime settings that test-session plugins may load from a local .env file."""

    for name in tuple(os.environ):
        if name.startswith("ATLASMIND_"):
            monkeypatch.delenv(name, raising=False)
