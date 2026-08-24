"""Owner and operations-authorized run, trace, and evaluation inspection."""

from dataclasses import dataclass

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.domain.common import ResourceNotAvailable
from atlasmind.identity.models import Action


@dataclass(frozen=True, slots=True)
class OperationalRunRecord:
    run_id: str
    principal_id: str
    correlation_id: str
    state: str
    trace_ref: str
    evaluation_run_ids: tuple[str, ...] = ()


class RunInspector:
    def __init__(self) -> None:
        self._records: dict[str, OperationalRunRecord] = {}

    def add(self, record: OperationalRunRecord) -> None:
        self._records[record.run_id] = record

    def get(self, run_id: str, context: AuthContext) -> OperationalRunRecord:
        record = self._records.get(run_id)
        if record is None or (
            record.principal_id != context.principal_id
            and Action.AUDIT not in context.allowed_actions
        ):
            raise ResourceNotAvailable()
        return record
