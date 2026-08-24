"""Relation construction, evidence binding, and conflict marking."""

from __future__ import annotations

from dataclasses import replace

from atlasmind.graph.models import GraphRelation, RelationEvidence, RelationStatus


def bind_relation(
    relation: GraphRelation,
    evidence: RelationEvidence,
) -> tuple[GraphRelation, RelationEvidence]:
    if relation.id != evidence.relation_id:
        raise ValueError("relation evidence binding mismatch")
    return relation, evidence


def mark_conflicts(relations: tuple[GraphRelation, ...]) -> tuple[GraphRelation, ...]:
    by_subject_type: dict[tuple[str, str], set[str]] = {}
    for relation in relations:
        by_subject_type.setdefault(
            (relation.source_entity_id, relation.relation_type),
            set(),
        ).add(relation.target_entity_id)
    return tuple(
        replace(relation, status=RelationStatus.CONFLICTED)
        if len(by_subject_type[(relation.source_entity_id, relation.relation_type)]) > 1
        else relation
        for relation in relations
    )
