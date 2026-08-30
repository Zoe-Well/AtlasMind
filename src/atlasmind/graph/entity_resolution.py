"""Alias-aware entity resolution with explicit ambiguity and merge approval."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from atlasmind.graph.models import EntityStatus, GraphEntity


def normalize_entity_name(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.casefold())


def normalized_entity_names(name: str, aliases: tuple[str, ...] = ()) -> frozenset[str]:
    """Return comparable non-empty keys for a canonical name and its aliases."""

    return frozenset(
        normalized for value in (name, *aliases) if (normalized := normalize_entity_name(value))
    )


@dataclass(frozen=True, slots=True)
class ResolutionCandidate:
    """Scored canonical candidate; scores are hints, not merge authority."""

    entity_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    lexical_score: float
    semantic_score: float

    @property
    def score(self) -> float:
        return max(self.lexical_score, self.semantic_score)


def choose_unambiguous_candidate(
    candidates: tuple[ResolutionCandidate, ...],
    *,
    minimum_score: float = 0.94,
    minimum_margin: float = 0.08,
) -> ResolutionCandidate | None:
    """Auto-resolve only a unique high-confidence candidate with a safe margin."""

    ordered = sorted(candidates, key=lambda item: (-item.score, item.entity_id))
    if not ordered or ordered[0].score < minimum_score:
        return None
    if len(ordered) > 1 and ordered[0].score - ordered[1].score < minimum_margin:
        return None
    return ordered[0]


def configured_canonical_name(
    name: str,
    aliases: tuple[str, ...],
    configured_aliases: dict[str, str],
) -> str:
    """Apply an administrator-confirmed alias mapping before fuzzy resolution."""

    normalized_mapping = {
        normalize_entity_name(alias): canonical
        for alias, canonical in configured_aliases.items()
        if normalize_entity_name(alias)
    }
    targets = {
        normalized_mapping[normalized]
        for value in (name, *aliases)
        if (normalized := normalize_entity_name(value)) in normalized_mapping
    }
    return next(iter(targets)) if len(targets) == 1 else name


class EntityResolver:
    def candidates(self, name: str, entities: tuple[GraphEntity, ...]) -> tuple[GraphEntity, ...]:
        normalized = normalize_entity_name(name)
        return tuple(
            entity
            for entity in entities
            if normalized in normalized_entity_names(entity.canonical_name, entity.aliases)
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
