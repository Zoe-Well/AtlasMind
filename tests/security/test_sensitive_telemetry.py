"""Sensitive query, chunk, prompt, and tool values never enter export artifacts."""

from __future__ import annotations

import json

import pytest

from atlasmind.observability.export_policy import ExportPolicy
from atlasmind.observability.langsmith_adapter import LangSmithAdapter


@pytest.mark.security
def test_secret_markers_are_removed_from_nested_telemetry_and_evaluation_artifacts() -> None:
    secret = "sk-atlasmind-do-not-export"
    policy = ExportPolicy(sensitive_values={secret})
    artifact = {
        "correlation_id": "correlation-1",
        "query": f"find account using {secret}",
        "chunk": {"content": f"internal password {secret}", "id": "chunk-1"},
        "prompt": f"system prompt {secret}",
        "tool": {"api_key": secret, "result": f"token={secret}"},
        "evaluation": {"failure_sample": f"answer exposed {secret}"},
    }

    sanitized = policy.sanitize(artifact)
    encoded = json.dumps(sanitized)

    assert secret not in encoded
    assert "password" not in encoded
    assert "api_key" not in encoded
    assert sanitized["correlation_id"] == "correlation-1"


@pytest.mark.security
def test_langsmith_is_disabled_by_default_and_uses_same_export_policy() -> None:
    secret = "tool-secret-value"
    adapter = LangSmithAdapter(ExportPolicy(sensitive_values={secret}), enabled=False)

    assert adapter.export({"correlation_id": "c-1", "tool_result": secret}) is None
    assert adapter.exported == ()
