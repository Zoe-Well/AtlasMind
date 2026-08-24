"""Hard Agent execution budgets and deterministic preflight checks."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentBudgets:
    max_steps: int = 12
    max_tools: int = 4
    timeout_ms: int = 60_000
    max_tokens: int = 16_000
    max_result_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if (
            min(
                self.max_steps,
                self.max_tools,
                self.timeout_ms,
                self.max_tokens,
                self.max_result_bytes,
            )
            <= 0
        ):
            raise ValueError("Agent budgets must be positive")

    def permits(self, *, steps: int, tools: int) -> bool:
        return steps <= self.max_steps and tools <= self.max_tools
