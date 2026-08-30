"""Neo4j GraphRAG projection and authorization-bounded retrieval."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

from neo4j import AsyncDriver, AsyncGraphDatabase, Driver, GraphDatabase
from neo4j.exceptions import Neo4jError
from neo4j_graphrag.experimental.components.kg_writer import KGWriter, KGWriterModel
from neo4j_graphrag.experimental.components.types import (
    LexicalGraphConfig,
    Neo4jGraph,
    Neo4jNode,
    Neo4jRelationship,
)
from neo4j_graphrag.indexes import create_vector_index
from neo4j_graphrag.retrievers import VectorCypherRetriever

ENTITY_VECTOR_INDEX = "atlasmind_entity_embedding"
ENTITY_VECTOR_PROPERTY = "embedding"
DEFAULT_LEXICAL_GRAPH_CONFIG = LexicalGraphConfig()


@dataclass(frozen=True, slots=True)
class GraphProjectionRecord:
    relation_id: str
    source_id: str
    source_name: str
    source_type: str
    source_embedding: tuple[float, ...]
    target_id: str
    target_name: str
    target_type: str
    target_embedding: tuple[float, ...]
    relation_type: str
    document_version_id: str
    chunk_id: str
    locator: str
    scope_ids: tuple[str, ...]
    generation: int
    confidence: float
    extraction_version: str = "unknown"
    policy_version: int = 1
    evidence_decision: str = "ELIGIBLE"
    source_aliases: tuple[str, ...] = ()
    target_aliases: tuple[str, ...] = ()
    source_document_id: str = ""


@dataclass(frozen=True, slots=True)
class RetrievedGraphPath:
    """Authorized bounded graph path with immutable source references."""

    entities: tuple[str, ...]
    relations: tuple[str, ...]
    directions: tuple[bool, ...]
    chunk_ids: tuple[str, ...]
    locators: tuple[str, ...]

    @property
    def fact(self) -> str:
        parts = [self.entities[0]]
        for relation, forward, entity in zip(
            self.relations, self.directions, self.entities[1:], strict=True
        ):
            parts.append(f"-[{relation}]-> {entity}" if forward else f"<-[{relation}]- {entity}")
        sources = ", ".join(
            f"{chunk_id}@{locator}"
            for chunk_id, locator in zip(self.chunk_ids, self.locators, strict=True)
        )
        return f"{' '.join(parts)} (sources={sources})"

    def as_dict(self) -> dict[str, object]:
        return {
            "entities": list(self.entities),
            "relations": list(self.relations),
            "directions": list(self.directions),
            "sources": [
                {"chunkId": chunk_id, "locator": locator}
                for chunk_id, locator in zip(self.chunk_ids, self.locators, strict=True)
            ],
        }


class AtlasMindKGWriter(KGWriter):
    """Incremental writer for the official Neo4jGraph/KGWriter contract.

    Neo4j GraphRAG's default experimental writer uses temporary per-run IDs. AtlasMind instead
    merges immutable PostgreSQL canonical IDs so repeated ingestion cannot duplicate entities.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def run(
        self,
        graph: Neo4jGraph,
        lexical_graph_config: LexicalGraphConfig = DEFAULT_LEXICAL_GRAPH_CONFIG,
    ) -> KGWriterModel:
        del lexical_graph_config
        node_rows = [
            {
                "id": node.id,
                "properties": node.properties,
                "embedding": node.embedding_properties.get(ENTITY_VECTOR_PROPERTY),
            }
            for node in graph.nodes
        ]
        relation_rows = [
            {
                "start_node_id": relation.start_node_id,
                "end_node_id": relation.end_node_id,
                "properties": relation.properties,
            }
            for relation in graph.relationships
        ]
        try:
            async with self._driver.session() as session:
                if node_rows:
                    await session.run(
                        """
                        UNWIND $rows AS row
                        MERGE (entity:Entity {canonical_id: row.id})
                        SET entity += row.properties,
                            entity.embedding = row.embedding
                        """,
                        rows=node_rows,
                    )
                if relation_rows:
                    await session.run(
                        """
                        UNWIND $rows AS row
                        MATCH (source:Entity {canonical_id: row.start_node_id})
                        MATCH (target:Entity {canonical_id: row.end_node_id})
                        MERGE (source)-[relation:RELATED {
                            canonical_id: row.properties.canonical_id
                        }]->(target)
                        SET relation += row.properties
                        """,
                        rows=relation_rows,
                    )
        except Neo4jError as exc:
            return KGWriterModel(status="FAILURE", metadata={"error": str(exc)})
        return KGWriterModel(
            status="SUCCESS",
            metadata={
                "statistics": {
                    "node_count": len(node_rows),
                    "relationship_count": len(relation_rows),
                }
            },
        )


class AtlasMindVectorCypherRetriever(VectorCypherRetriever):
    """Compatibility shim for neo4j-graphrag 1.18 index-property naming.

    The base index loader stores ``_embedding_node_property`` while this retriever reads
    ``_node_embedding_property`` when metadata filters use exact vector search on Neo4j 5.x.
    """

    def _fetch_index_infos(self, vector_index_name: str) -> None:
        super()._fetch_index_infos(vector_index_name)
        self._node_embedding_property = getattr(self, "_embedding_node_property", None)


class Neo4jRuntime:
    def __init__(self, *, uri: str, username: str, password: str) -> None:
        auth = (username, password)
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=auth)
        self._sync_driver: Driver = GraphDatabase.driver(uri, auth=auth)
        self._writer = AtlasMindKGWriter(self._driver)
        self._retriever: AtlasMindVectorCypherRetriever | None = None
        self._retriever_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._driver.close()
        await asyncio.to_thread(self._sync_driver.close)

    async def verify(self) -> None:
        await self._driver.verify_connectivity()
        async with self._driver.session() as session:
            await session.run(
                "CREATE CONSTRAINT entity_canonical_id IF NOT EXISTS "
                "FOR (entity:Entity) REQUIRE entity.canonical_id IS UNIQUE"
            )

    async def project(self, records: tuple[GraphProjectionRecord, ...]) -> int:
        if not records:
            return 0
        graph = self._to_framework_graph(records)
        result = await self._writer.run(graph)
        if result.status != "SUCCESS":
            error = (result.metadata or {}).get("error", "unknown Neo4j GraphRAG writer failure")
            raise RuntimeError(str(error))
        dimension = len(records[0].source_embedding)
        if dimension <= 0:
            raise ValueError("entity embedding must be non-empty")
        if any(
            len(vector) != dimension
            for record in records
            for vector in (record.source_embedding, record.target_embedding)
        ):
            raise ValueError("entity embedding dimensions must be consistent")
        await asyncio.to_thread(self._create_vector_index, dimension)
        return len(records)

    async def retrieve_paths(
        self,
        query: str,
        *,
        query_embedding: list[float],
        scope_ids: frozenset[str],
        document_version_ids: frozenset[str],
        limit: int = 24,
        seed_limit: int = 8,
        max_hops: int = 2,
        max_nodes: int = 40,
        allowed_entity_types: frozenset[str] = frozenset(),
        allowed_relation_types: frozenset[str] = frozenset(),
        minimum_confidence: float = 0.0,
    ) -> tuple[RetrievedGraphPath, ...]:
        if not scope_ids or not document_version_ids or not query_embedding:
            return ()
        authorized_ids = await self._authorized_entity_ids(
            scope_ids=scope_ids,
            document_version_ids=document_version_ids,
            allowed_entity_types=allowed_entity_types,
            allowed_relation_types=allowed_relation_types,
            minimum_confidence=minimum_confidence,
        )
        if not authorized_ids:
            return ()
        retriever = await self._get_retriever()
        name_seed_ids = await self._name_seed_entity_ids(
            query,
            authorized_ids=authorized_ids,
            limit=seed_limit,
        )
        seed_groups = [name_seed_ids, authorized_ids] if name_seed_ids else [authorized_ids]
        rows: list[dict[str, object]] = []
        for seed_ids in seed_groups:
            result = await asyncio.to_thread(
                retriever.get_search_results,
                query_vector=query_embedding,
                top_k=min(seed_limit, len(seed_ids)),
                filters={"canonical_id": {"$in": sorted(seed_ids)}},
                query_params={
                    "scope_ids": sorted(scope_ids),
                    "version_ids": sorted(document_version_ids),
                    "fact_limit": limit,
                    "max_hops": max_hops,
                    "allowed_entity_types": sorted(allowed_entity_types),
                    "allowed_relation_types": sorted(allowed_relation_types),
                    "minimum_confidence": minimum_confidence,
                },
            )
            rows.extend(record.data() for record in result.records)
        paths: list[RetrievedGraphPath] = []
        seen: set[tuple[tuple[str, ...], tuple[str, ...], tuple[bool, ...], tuple[str, ...]]] = (
            set()
        )
        expanded_nodes: set[str] = set()
        for row in rows:
            if "nodes" in row:
                entities = tuple(map(str, cast(list[object], row.get("nodes") or [])))
                relations = tuple(map(str, cast(list[object], row.get("relations") or [])))
                directions = tuple(map(bool, cast(list[object], row.get("directions") or [])))
                chunk_ids = tuple(map(str, cast(list[object], row.get("chunk_ids") or [])))
                locators = tuple(map(str, cast(list[object], row.get("locators") or [])))
            else:
                entities = (str(row["source"]), str(row["target"]))
                relations = (str(row["relation_type"]),)
                directions = (True,)
                chunk_ids = (str(row["chunk_id"]),)
                locators = (str(row["locator"]),)
            if (
                len(entities) != len(relations) + 1
                or len(directions) != len(relations)
                or len(chunk_ids) != len(relations)
                or len(locators) != len(relations)
            ):
                continue
            identity = (entities, relations, directions, chunk_ids)
            if identity in seen:
                continue
            candidate_nodes = expanded_nodes | set(entities)
            if len(candidate_nodes) > max_nodes:
                continue
            seen.add(identity)
            expanded_nodes = candidate_nodes
            paths.append(RetrievedGraphPath(entities, relations, directions, chunk_ids, locators))
            if len(paths) >= limit:
                break
        return tuple(paths)

    async def _name_seed_entity_ids(
        self,
        query: str,
        *,
        authorized_ids: frozenset[str],
        limit: int,
    ) -> frozenset[str]:
        if getattr(self, "_driver", None) is None:  # pragma: no cover - driverless unit doubles
            return frozenset()
        terms = tuple(
            dict.fromkeys(
                value.casefold()
                for value in query.replace("/", " ").replace("_", " ").split()
                if len(value.strip()) >= 2
            )
        )[:20]
        if not terms:
            return frozenset()
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (entity:Entity)
                WHERE entity.canonical_id IN $authorized_ids
                  AND any(term IN $terms WHERE
                      toLower(entity.name) CONTAINS term OR
                      any(alias IN coalesce(entity.aliases, []) WHERE
                          toLower(alias) CONTAINS term))
                RETURN entity.canonical_id AS canonical_id
                ORDER BY entity.name, entity.canonical_id
                LIMIT $limit
                """,
                authorized_ids=sorted(authorized_ids),
                terms=list(terms),
                limit=limit,
            )
            rows = await result.data()
        return frozenset(str(row["canonical_id"]) for row in rows)

    async def facts(
        self,
        query: str,
        *,
        query_embedding: list[float],
        scope_ids: frozenset[str],
        document_version_ids: frozenset[str],
        limit: int = 30,
    ) -> tuple[str, ...]:
        paths = await self.retrieve_paths(
            query,
            query_embedding=query_embedding,
            scope_ids=scope_ids,
            document_version_ids=document_version_ids,
            limit=limit,
        )
        return tuple(path.fact for path in paths)

    async def revoke_document_version(self, version_id: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                "MATCH ()-[relation:RELATED]->() "
                "WHERE relation.document_version_id = $version_id "
                "SET relation.active = false",
                version_id=version_id,
            )

    async def reconcile_active_versions(self, version_ids: frozenset[str]) -> None:
        """Idempotently align the rebuildable Neo4j projection with canonical PostgreSQL state."""

        async with self._driver.session() as session:
            await session.run(
                """
                MATCH ()-[relation:RELATED]->()
                SET relation.active =
                    relation.document_version_id IN $version_ids
                    AND relation.evidence_decision = 'ELIGIBLE'
                """,
                version_ids=sorted(version_ids),
            )

    async def _authorized_entity_ids(
        self,
        *,
        scope_ids: frozenset[str],
        document_version_ids: frozenset[str],
        allowed_entity_types: frozenset[str] = frozenset(),
        allowed_relation_types: frozenset[str] = frozenset(),
        minimum_confidence: float = 0.0,
    ) -> frozenset[str]:
        async with self._driver.session() as session:
            result = await session.run(
                """
            MATCH (source:Entity)-[relation:RELATED]->(target:Entity)
            WHERE relation.active = true
              AND relation.evidence_decision = 'ELIGIBLE'
              AND relation.confidence >= $minimum_confidence
              AND relation.document_version_id IN $version_ids
              AND all(scope IN relation.scope_ids WHERE scope IN $scope_ids)
              AND (size($allowed_relation_types) = 0 OR
                   relation.relation_type IN $allowed_relation_types)
              AND (size($allowed_entity_types) = 0 OR
                   (source.entity_type IN $allowed_entity_types AND
                    target.entity_type IN $allowed_entity_types))
                UNWIND [source.canonical_id, target.canonical_id] AS canonical_id
                RETURN DISTINCT canonical_id
                """,
                scope_ids=sorted(scope_ids),
                version_ids=sorted(document_version_ids),
                allowed_entity_types=sorted(allowed_entity_types),
                allowed_relation_types=sorted(allowed_relation_types),
                minimum_confidence=minimum_confidence,
            )
            rows = await result.data()
        return frozenset(str(row["canonical_id"]) for row in rows)

    async def _get_retriever(self) -> AtlasMindVectorCypherRetriever:
        if self._retriever is not None:
            return self._retriever
        async with self._retriever_lock:
            if self._retriever is None:
                self._retriever = await asyncio.to_thread(
                    AtlasMindVectorCypherRetriever,
                    self._sync_driver,
                    ENTITY_VECTOR_INDEX,
                    self._retrieval_query(),
                )
        return self._retriever

    def _create_vector_index(self, dimension: int) -> None:
        create_vector_index(
            self._sync_driver,
            ENTITY_VECTOR_INDEX,
            label="Entity",
            embedding_property=ENTITY_VECTOR_PROPERTY,
            dimensions=dimension,
            similarity_fn="cosine",
            fail_if_exists=False,
        )

    @staticmethod
    def _retrieval_query() -> str:
        return """
        MATCH path=(node)-[path_relations:RELATED*1..2]-(target:Entity)
        WHERE all(relation IN path_relations WHERE
          relation.active = true
          AND relation.evidence_decision = 'ELIGIBLE'
          AND relation.confidence >= $minimum_confidence
          AND relation.document_version_id IN $version_ids
          AND all(scope IN relation.scope_ids WHERE scope IN $scope_ids)
          AND (size($allowed_relation_types) = 0 OR
               relation.relation_type IN $allowed_relation_types))
          AND length(path) <= $max_hops
          AND all(entity IN nodes(path) WHERE
              size($allowed_entity_types) = 0 OR
              entity.entity_type IN $allowed_entity_types)
        WITH path, path_relations, score,
             reduce(confidence = 1.0, relation IN path_relations |
               confidence * relation.confidence) AS path_confidence
        RETURN [entity IN nodes(path) | entity.name] AS nodes,
               [relation IN path_relations | relation.relation_type] AS relations,
               [index IN range(0, size(path_relations) - 1) |
                 startNode(path_relations[index]) = nodes(path)[index]] AS directions,
               [relation IN path_relations | relation.chunk_id] AS chunk_ids,
               [relation IN path_relations | relation.locator] AS locators,
               score AS score
        ORDER BY length(path) ASC, score DESC, path_confidence DESC
        LIMIT $fact_limit
        """

    @staticmethod
    def _to_framework_graph(records: tuple[GraphProjectionRecord, ...]) -> Neo4jGraph:
        nodes: dict[str, Neo4jNode] = {}
        relationships: list[Neo4jRelationship] = []
        for record in records:
            nodes[record.source_id] = Neo4jNode(
                id=record.source_id,
                label="Entity",
                properties={
                    "canonical_id": record.source_id,
                    "name": record.source_name,
                    "entity_type": record.source_type,
                    "aliases": list(record.source_aliases),
                },
                embedding_properties={ENTITY_VECTOR_PROPERTY: list(record.source_embedding)},
            )
            nodes[record.target_id] = Neo4jNode(
                id=record.target_id,
                label="Entity",
                properties={
                    "canonical_id": record.target_id,
                    "name": record.target_name,
                    "entity_type": record.target_type,
                    "aliases": list(record.target_aliases),
                },
                embedding_properties={ENTITY_VECTOR_PROPERTY: list(record.target_embedding)},
            )
            relationships.append(
                Neo4jRelationship(
                    start_node_id=record.source_id,
                    end_node_id=record.target_id,
                    type="RELATED",
                    properties={
                        # A canonical semantic relation can be supported by multiple document
                        # versions.  Neo4j must keep each provenance edge independent so that
                        # revoking one version cannot deactivate evidence from another.
                        "canonical_id": ":".join(
                            (
                                record.relation_id,
                                record.document_version_id,
                                record.chunk_id,
                            )
                        ),
                        "relation_id": record.relation_id,
                        "relation_type": record.relation_type,
                        "document_version_id": record.document_version_id,
                        "source_document_id": record.source_document_id,
                        "chunk_id": record.chunk_id,
                        "locator": record.locator,
                        "scope_ids": list(record.scope_ids),
                        "generation": record.generation,
                        "confidence": record.confidence,
                        "extraction_version": record.extraction_version,
                        "policy_version": record.policy_version,
                        "evidence_decision": record.evidence_decision,
                        "active": True,
                    },
                )
            )
        return Neo4jGraph(nodes=list(nodes.values()), relationships=relationships)
