"""Neo4j GraphRAG projection and authorization-bounded retrieval."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

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

    async def facts(
        self,
        query: str,
        *,
        query_embedding: list[float],
        scope_ids: frozenset[str],
        document_version_ids: frozenset[str],
        limit: int = 30,
    ) -> tuple[str, ...]:
        del query
        if not scope_ids or not document_version_ids or not query_embedding:
            return ()
        authorized_ids = await self._authorized_entity_ids(
            scope_ids=scope_ids,
            document_version_ids=document_version_ids,
        )
        if not authorized_ids:
            return ()
        retriever = await self._get_retriever()
        result = await asyncio.to_thread(
            retriever.get_search_results,
            query_vector=query_embedding,
            top_k=min(limit, len(authorized_ids)),
            filters={"canonical_id": {"$in": sorted(authorized_ids)}},
            query_params={
                "scope_ids": sorted(scope_ids),
                "version_ids": sorted(document_version_ids),
                "fact_limit": limit,
            },
        )
        rows = [record.data() for record in result.records]
        return tuple(
            f"{row['source']} -[{row['relation_type']}]-> {row['target']} "
            f"(source={row['chunk_id']} locator={row['locator']})"
            for row in rows
        )

    async def revoke_document_version(self, version_id: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                "MATCH ()-[relation:RELATED]->() "
                "WHERE relation.document_version_id = $version_id "
                "SET relation.active = false",
                version_id=version_id,
            )

    async def _authorized_entity_ids(
        self,
        *,
        scope_ids: frozenset[str],
        document_version_ids: frozenset[str],
    ) -> frozenset[str]:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (source:Entity)-[relation:RELATED]->(target:Entity)
                WHERE relation.active = true
                  AND relation.document_version_id IN $version_ids
                  AND all(scope IN relation.scope_ids WHERE scope IN $scope_ids)
                UNWIND [source.canonical_id, target.canonical_id] AS canonical_id
                RETURN DISTINCT canonical_id
                """,
                scope_ids=sorted(scope_ids),
                version_ids=sorted(document_version_ids),
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
        MATCH (source:Entity)-[relation:RELATED]->(target:Entity)
        WHERE (source = node OR target = node)
          AND relation.active = true
          AND relation.document_version_id IN $version_ids
          AND all(scope IN relation.scope_ids WHERE scope IN $scope_ids)
        RETURN source.name AS source,
               relation.relation_type AS relation_type,
               target.name AS target,
               relation.chunk_id AS chunk_id,
               relation.locator AS locator,
               score AS score
        ORDER BY score DESC, relation.confidence DESC
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
                },
                embedding_properties={ENTITY_VECTOR_PROPERTY: list(record.target_embedding)},
            )
            relationships.append(
                Neo4jRelationship(
                    start_node_id=record.source_id,
                    end_node_id=record.target_id,
                    type="RELATED",
                    properties={
                        "canonical_id": record.relation_id,
                        "relation_type": record.relation_type,
                        "document_version_id": record.document_version_id,
                        "chunk_id": record.chunk_id,
                        "locator": record.locator,
                        "scope_ids": list(record.scope_ids),
                        "generation": record.generation,
                        "confidence": record.confidence,
                        "active": True,
                    },
                )
            )
        return Neo4jGraph(nodes=list(nodes.values()), relationships=relationships)
