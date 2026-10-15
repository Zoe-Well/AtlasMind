"""Read-only, real-model retrieval comparison over short FAQs and detailed manuals.

Measures expected-source recall, not answer correctness; no graph or business writes.
Run inside the configured backend: python -m tests.evaluation.retrieval_comparison --report ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import UUID

from sqlalchemy import text

from atlasmind.api.service import MeteredModel, ServiceKnowledge
from atlasmind.retrieval.advanced_workflow import AdvancedRetrievalWorkflow
from atlasmind.retrieval.strategy_policy import RetrievalPlan, StrategySelection
from atlasmind.runtime import create_runtime
from atlasmind.settings import load_settings


async def run(report: Path) -> None:
    settings = load_settings()
    runtime = create_runtime(settings)
    service = ServiceKnowledge(runtime, str(settings.service_scope_id), standard=True)
    questions = [
        json.loads(line)
        for line in Path("tests/fixtures/evaluation/yifulu_mvp.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    questions.extend(
        json.loads(line)
        for line in Path("tests/fixtures/evaluation/yifulu_retrieval_extended.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    modes = {
        "vector": ("vector",),
        "lexical": ("bm25",),
        "hybrid": ("vector", "bm25"),
        "rerank": ("vector", "bm25"),
        "neighbors": ("vector", "bm25"),
    }
    rows = []
    try:
        async with service.sessions() as session:
            corpus = (
                (
                    await session.execute(
                        text("""
                SELECT d.id,d.title,v.id AS version_id,count(c.id) AS chunks
                FROM knowledge_documents d JOIN document_versions v ON v.id=d.active_version_id
                JOIN knowledge_chunks c ON c.document_version_id=v.id
                WHERE d.active AND v.searchable AND c.active AND c.scope_ids <@ :scopes
                GROUP BY d.id,v.id ORDER BY d.id
            """),
                        {"scopes": [UUID(s) for s in service.scopes]},
                    )
                )
                .mappings()
                .all()
            )
        for question in questions:
            for mode, retrievers in modes.items():
                runtime.ai.query_embedding_cache.values.clear()
                meter = MeteredModel(runtime.ai)
                workflow = AdvancedRetrievalWorkflow(service.sessions, meter, runtime.graph)
                plan = RetrievalPlan(
                    reasonCode="EVALUATION",
                    retrievers=tuple(StrategySelection(id=s) for s in retrievers),
                    postRetrieval=(StrategySelection(id="rerank"),) if mode == "rerank" else (),
                )
                started = perf_counter()
                result = await workflow.run(
                    question["query"],
                    mode="SIMPLE",
                    limit=5,
                    scopes=service.scopes,
                    authz_revision=1,
                    policy_override=service.policy,
                    fixed_plan=plan,
                    expand_neighbors=mode == "neighbors",
                )
                elapsed = round((perf_counter() - started) * 1000)
                authorized = await service.rows(
                    [UUID(e.source.canonical_id) for e in result.evidence]
                )
                titles = [
                    authorized[e.source.canonical_id]["title"]
                    for e in result.evidence
                    if e.source.canonical_id in authorized
                ]
                rank = next(
                    (i + 1 for i, title in enumerate(titles) if title == question["title"]), None
                )
                row = {
                    "query": question["query"],
                    "mode": mode,
                    "elapsed_ms": elapsed,
                    "expected_title_rank": rank,
                    "titles": titles,
                    "metrics": result.metrics,
                    "usage": dict(meter.counts),
                    "warnings": result.warnings,
                    "reason": result.reason_code,
                }
                if mode == "hybrid":
                    warm = await workflow.run(
                        question["query"],
                        mode="SIMPLE",
                        limit=5,
                        scopes=service.scopes,
                        authz_revision=1,
                        policy_override=service.policy,
                        fixed_plan=plan,
                    )
                    row["warm_query_cache_hits"] = warm.metrics.get("query_cache_hits", 0)
                rows.append(row)
            print(
                json.dumps({"completed_questions": len(rows) // len(modes)}, ensure_ascii=False),
                flush=True,
            )
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps(
                    {"corpus": [dict(r) for r in corpus], "rows": rows},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        summary = {}
        for mode in modes:
            selected = [r for r in rows if r["mode"] == mode]
            summary[mode] = {
                "cases": len(selected),
                "source_hit_at_5": sum(r["expected_title_rank"] is not None for r in selected),
                "mrr": round(
                    sum(1 / r["expected_title_rank"] for r in selected if r["expected_title_rank"])
                    / len(selected),
                    3,
                ),
                "median_ms": median(r["elapsed_ms"] for r in selected),
                "max_ms": max(r["elapsed_ms"] for r in selected),
                "degraded": sum(bool(r["warnings"]) for r in selected),
            }
        report.write_text(
            json.dumps(
                {"summary": summary, "corpus": [dict(r) for r in corpus], "rows": rows},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    finally:
        await runtime.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    asyncio.run(run(parser.parse_args().report))
