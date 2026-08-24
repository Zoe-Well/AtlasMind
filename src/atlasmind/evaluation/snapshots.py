"""Canonical evaluation manifest and reproducible configuration digest."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True, slots=True)
class EvaluationManifest:
    code_version: str
    dataset: str
    knowledge_snapshot: str
    index_generation: str
    retrieval_policy: str
    model: str
    prompt: str
    evaluator: str
    seed: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return f"sha256:{sha256(encoded).hexdigest()}"
