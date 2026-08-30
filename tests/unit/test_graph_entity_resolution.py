"""Cross-document entity normalization and ambiguity boundaries."""

from atlasmind.graph.entity_resolution import (
    EntityResolver,
    ResolutionCandidate,
    choose_unambiguous_candidate,
    configured_canonical_name,
    normalized_entity_names,
)
from atlasmind.graph.models import GraphEntity


def test_incoming_alias_can_link_a_cross_document_entity() -> None:
    existing = GraphEntity("PostgreSQL", "SYSTEM", aliases=("Postgres DB",))

    incoming = normalized_entity_names("Postgres", ("PostgreSQL",))
    existing_names = normalized_entity_names(existing.canonical_name, existing.aliases)

    assert incoming & existing_names == {"postgresql"}
    assert EntityResolver().resolve("Postgres DB", (existing,)) == existing


def test_ambiguous_alias_is_not_silently_resolved() -> None:
    candidates = (
        GraphEntity("Aurora Project", "PROJECT", aliases=("Aurora",)),
        GraphEntity("Aurora Platform", "PROJECT", aliases=("Aurora",)),
    )

    assert EntityResolver().resolve("Aurora", candidates) is None


def test_configured_alias_precedes_fuzzy_resolution() -> None:
    assert (
        configured_canonical_name(
            "PG",
            ("Postgres",),
            {"pg": "PostgreSQL"},
        )
        == "PostgreSQL"
    )


def test_scored_resolution_requires_threshold_and_safe_margin() -> None:
    clear = (
        ResolutionCandidate("a", "PostgreSQL", (), 0.98, 0.96),
        ResolutionCandidate("b", "PostgREST", (), 0.80, 0.82),
    )
    ambiguous = (
        ResolutionCandidate("a", "Aurora DB", (), 0.96, 0.94),
        ResolutionCandidate("b", "Aurora Service", (), 0.93, 0.95),
    )

    assert choose_unambiguous_candidate(clear) == clear[0]
    assert choose_unambiguous_candidate(ambiguous) is None
