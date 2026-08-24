"""Minimal append-only audit events with a deterministic hash chain."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any

from atlasmind.domain.common import new_id, utc_now


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_type: str
    actor_principal_id: str
    correlation_id: str
    decision: str
    reason_code: str
    resource_type: str
    resource_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=new_id)
    occurred_at: datetime = field(default_factory=utc_now)
    previous_hash: str = "sha256:genesis"
    classification: str = "CONFIDENTIAL"

    def canonical_payload(self) -> bytes:
        data = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "actor_principal_id": self.actor_principal_id,
            "correlation_id": self.correlation_id,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
            "classification": self.classification,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    @property
    def event_hash(self) -> str:
        return f"sha256:{sha256(self.canonical_payload()).hexdigest()}"
