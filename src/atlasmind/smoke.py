"""Machine-readable real MVP smoke test for the local Compose environment."""

# ruff: noqa: E501, RUF001 -- SQL and Chinese smoke fixtures stay readable inline.

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID, uuid4

from opentelemetry import trace
from sqlalchemy import text

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.identity.models import Action
from atlasmind.observability.telemetry import configure_telemetry
from atlasmind.runtime import LOCAL_PRINCIPAL_ID, LOCAL_SCOPE_ID, Runtime, create_runtime
from atlasmind.settings import load_settings


def _auth_context(correlation_id: str) -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id=LOCAL_PRINCIPAL_ID,
        role_codes=frozenset({"local-super-admin"}),
        scope_ids=frozenset({LOCAL_SCOPE_ID}),
        allowed_actions=frozenset(Action),
        authz_revision=1,
        policy_revision=1,
        correlation_id=correlation_id,
        issued_at=now,
        expires_at=now + timedelta(hours=8),
    )


async def _wait_for_searchable(
    runtime: Runtime, job_id: str, timeout_seconds: int = 180
) -> dict[str, object]:
    deadline = monotonic() + timeout_seconds
    knowledge = runtime.knowledge
    while monotonic() < deadline:
        job = await knowledge.get_job(job_id)
        if job["state"] == "SEARCHABLE":
            return job
        if job["state"] in {"FAILED", "CANCELLED"}:
            raise RuntimeError(f"ingestion ended in {job['state']}: {job.get('failure')}")
        await knowledge.process_next()
        await asyncio.sleep(1)
    raise TimeoutError("ingestion did not become searchable within 180 seconds")


async def run_smoke() -> dict[str, object]:
    settings = load_settings()
    configure_telemetry(
        "atlasmind-smoke",
        str(settings.otel_exporter_otlp_endpoint) if settings.otel_exporter_otlp_endpoint else None,
    )
    tracer = trace.get_tracer("atlasmind.smoke")
    source_key = f"smoke/real-mvp/{uuid4()}"
    upload_correlation = str(uuid4())
    run_correlation = str(uuid4())
    runtime = create_runtime(settings)
    await runtime.verify()
    restarted = None
    document_id = ""
    revoked = False
    stale_cleaned = 0
    try:
        existing = await runtime.knowledge.list_documents(frozenset({LOCAL_SCOPE_ID}), limit=200)
        existing_items = existing["items"]
        if not isinstance(existing_items, list):
            raise RuntimeError("document list response is invalid")
        for item in existing_items:
            if not isinstance(item, dict):
                raise RuntimeError("document list item is invalid")
            if item["status"] == "ACTIVE" and str(item["sourceKey"]).startswith("smoke/real-mvp/"):
                await runtime.knowledge.revoke_document(
                    str(item["id"]),
                    frozenset({LOCAL_SCOPE_ID}),
                    actor_id=LOCAL_PRINCIPAL_ID,
                    correlation_id=str(uuid4()),
                )
                stale_cleaned += 1
        accepted = await runtime.knowledge.upload(
            title="AtlasMind 真实链路烟雾测试",
            source_key=source_key,
            file_name="atlasmind-smoke.md",
            media_type="text/markdown",
            content=(
                "# AtlasMind 真实链路\n\n"
                "AtlasMind 使用 PostgreSQL 保存规范知识状态，使用 MinIO 保存原始文件，"
                "并将实体关系投影到 Neo4j。"
            ).encode(),
            scope_ids=frozenset({LOCAL_SCOPE_ID}),
            metadata={"classification": "INTERNAL", "businessOwner": "local-super-admin"},
            actor_id=LOCAL_PRINCIPAL_ID,
            idempotency_key=str(uuid4()),
            correlation_id=upload_correlation,
        )
        document_id = str(accepted["document"]["id"])  # type: ignore[index]
        version_id = str(accepted["versionId"])
        job_id = str(accepted["ingestionJob"]["id"])  # type: ignore[index]
        job = await _wait_for_searchable(runtime, job_id)

        async with runtime.engine.connect() as connection:
            storage = (
                await connection.execute(
                    text(
                        """
                        SELECT version.object_key,
                               (SELECT count(*) FROM knowledge_chunks WHERE document_version_id = version.id) AS chunks,
                               (SELECT count(*) FROM graph_entities entity
                                 JOIN entity_mentions mention ON mention.entity_id = entity.id
                                WHERE mention.document_version_id = version.id) AS entities,
                               (SELECT count(*) FROM audit_events WHERE correlation_id = :correlation) AS upload_audits
                          FROM document_versions version WHERE version.id = :version_id
                        """
                    ),
                    {"version_id": UUID(version_id), "correlation": UUID(upload_correlation)},
                )
            ).mappings().one()
        original = await runtime.object_store.get_bytes(str(storage["object_key"]))
        if not original or int(storage["chunks"]) < 1 or int(storage["entities"]) < 1:
            raise RuntimeError("persistent projections are incomplete")

        await runtime.close()
        restarted = create_runtime(settings)
        await restarted.verify()
        with tracer.start_as_current_span("atlasmind.smoke.agent_run") as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
        answer = await restarted.knowledge.ask(
            query="AtlasMind 使用哪些系统保存规范知识、原始文件和实体关系？",
            mode="GRAPH",
            context=_auth_context(run_correlation),
            trace_id=trace_id,
        )
        citations = answer["answer"]["citations"]  # type: ignore[index]
        if not citations:
            raise RuntimeError("authorized answer returned no citations")
        async with restarted.engine.connect() as connection:
            run_records = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            (SELECT count(*) FROM evidence_records WHERE run_id = :run_id) AS evidence,
                            (SELECT count(*) FROM citations WHERE run_id = :run_id) AS citations,
                            (SELECT count(*) FROM audit_events WHERE correlation_id = :correlation) AS audits,
                            (SELECT count(*) FROM agent_runs WHERE id = :run_id AND trace_id = :trace_id) AS traces
                        """
                    ),
                    {
                        "run_id": UUID(str(answer["id"])),
                        "correlation": UUID(run_correlation),
                        "trace_id": trace_id,
                    },
                )
            ).mappings().one()
        if min(int(run_records[name]) for name in ("evidence", "citations", "audits", "traces")) < 1:
            raise RuntimeError("run evidence or audit correlation is incomplete")

        await restarted.knowledge.revoke_document(
            document_id,
            frozenset({LOCAL_SCOPE_ID}),
            actor_id=LOCAL_PRINCIPAL_ID,
            correlation_id=str(uuid4()),
        )
        revoked = True
        after_revoke = await restarted.knowledge.ask(
            query="AtlasMind 使用哪些系统保存规范知识？",
            mode="GRAPH",
            context=_auth_context(str(uuid4())),
        )
        revoked_citations = after_revoke["answer"]["citations"]  # type: ignore[index]
        if any(item["source"]["version"] == version_id for item in revoked_citations):
            raise RuntimeError("revoked evidence remained searchable")
        return {
            "status": "passed",
            "dataMode": "persistent",
            "documentId": document_id,
            "versionId": version_id,
            "jobState": job["state"],
            "checks": {
                "minioOriginal": True,
                "postgresChunks": int(storage["chunks"]),
                "neo4jProjectionSourceEntities": int(storage["entities"]),
                "authorizedCitations": len(citations),
                "runAuditCorrelation": int(run_records["audits"]),
                "persistedTrace": trace_id,
                "restartRetrieval": True,
                "revocationFiltering": True,
                "staleSmokeDocumentsRevoked": stale_cleaned,
            },
        }
    finally:
        target = restarted or runtime
        if document_id and not revoked:
            with suppress(Exception):
                await target.knowledge.revoke_document(
                    document_id,
                    frozenset({LOCAL_SCOPE_ID}),
                    actor_id=LOCAL_PRINCIPAL_ID,
                    correlation_id=str(uuid4()),
                )
        await target.close()


def main() -> None:
    try:
        report = asyncio.run(run_smoke())
    except Exception as exc:
        report = {"status": "failed", "errorType": type(exc).__name__, "message": str(exc)}
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
