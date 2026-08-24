"""Allowlisted external API adapter with injected transport and bounded responses."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from atlasmind.domain.common import AuthorizationDenied, BudgetExceeded

ExternalTransport = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ExternalEndpoint:
    name: str
    method: str
    url: str
    timeout_ms: int
    max_result_bytes: int
    side_effect: bool = False


class ExternalApiAdapter:
    def __init__(
        self,
        endpoints: tuple[ExternalEndpoint, ...],
        transport: ExternalTransport,
    ) -> None:
        self._endpoints = {item.name: item for item in endpoints}
        self._transport = transport

    async def invoke(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = self._endpoints.get(name)
        if endpoint is None:
            raise AuthorizationDenied(details={"reason": "ENDPOINT_NOT_AVAILABLE"})
        try:
            result = await asyncio.wait_for(
                self._transport(endpoint.method, endpoint.url, payload),
                timeout=endpoint.timeout_ms / 1_000,
            )
        except TimeoutError as exc:
            raise BudgetExceeded(details={"reason": "TIMED_OUT"}) from exc
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > endpoint.max_result_bytes:
            raise BudgetExceeded(details={"reason": "RESULT_BUDGET_EXCEEDED"})
        return result
