"""Alias-aware entity resolution with explicit ambiguity and merge approval."""

from __future__ import annotations

import re
from dataclasses import replace

from atlasmind.graph.models import EntityStatus, GraphEntity


def normalize_entity_name(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.casefold())


class EntityResolver:
    def candidates(self, name: str, entities: tuple[GraphEntity, ...]) -> tuple[GraphEntity, ...]:
        normalized = normalize_entity_name(name)
        return tuple(
            entity
            for entity in entities
            if normalized
            in {
                normalize_entity_name(entity.canonical_name),
                *(normalize_entity_name(alias) for alias in entity.aliases),
            }
            and entity.status is EntityStatus.ACTIVE
        )

    def resolve(self, name: str, entities: tuple[GraphEntity, ...]) -> GraphEntity | None:
        candidates = self.candidates(name, entities)
        return candidates[0] if len(candidates) == 1 else None

    def merge(
        self,
        source: GraphEntity,
        target: GraphEntity,
        *,
        approved: bool,
    ) -> GraphEntity:
        if not approved:
            raise ValueError("entity merge requires explicit approval")
        if source.id == target.id:
            raise ValueError("entity cannot merge into itself")
        return replace(source, status=EntityStatus.MERGED, merged_into_id=target.id)
