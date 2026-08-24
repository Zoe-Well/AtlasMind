"""Agent nodes may only emit and execute typed CapabilityRequest values."""

from __future__ import annotations

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.identity.models import AuthorizationSnapshot
from atlasmind.tools.contracts import CapabilityRequest, CapabilityResult
from atlasmind.tools.execution_gateway import ExecutionGateway


async def execute_capability_node(
    request: CapabilityRequest,
    *,
    gateway: ExecutionGateway,
    context: AuthContext,
    current: AuthorizationSnapshot,
) -> CapabilityResult:
    return await gateway.execute(request, context, current)
