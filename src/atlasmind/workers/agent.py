"""Queue worker for bounded Agent runs with approval pause and terminal isolation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from atlasmind.agent.models import AgentRunState
from atlasmind.infrastructure.repositories.agent_runs import (
    InMemoryAgentRunRepository,
    PersistedAgentRun,
)

RunProcessor = Callable[[PersistedAgentRun], Awaitable[AgentRunState]]


class AgentWorker:
    def __init__(
        self,
        repository: InMemoryAgentRunRepository,
        processor: RunProcessor,
    ) -> None:
        self._repository = repository
        self._processor = processor

    async def run_once(self) -> PersistedAgentRun | None:
        queued = next(
            (item for item in self._repository.runs.values() if item.state is AgentRunState.QUEUED),
            None,
        )
        if queued is None:
            return None
        running = self._repository.update_state(queued.id, AgentRunState.RUNNING)
        try:
            state = await self._processor(running)
        except TimeoutError:
            state = AgentRunState.TIMED_OUT
        except Exception:
            state = AgentRunState.FAILED
        return self._repository.update_state(running.id, state)

    def resume_after_approval(self, run_id: str) -> PersistedAgentRun:
        run = self._repository.get(run_id)
        if run.state is not AgentRunState.WAITING_APPROVAL:
            return run
        return self._repository.update_state(run_id, AgentRunState.QUEUED)

    def cancel(self, run_id: str) -> PersistedAgentRun:
        return self._repository.update_state(run_id, AgentRunState.CANCELLED)
