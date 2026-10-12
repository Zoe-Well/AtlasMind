"""Import already-published common FAQs once and evaluate the restricted real service.

Input is the reviewed public/customer_service export, never a business database dump.
Existing AtlasMind documents are preserved on reruns; later edits live in AtlasMind.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path
from time import monotonic, time

import httpx
import jwt

from atlasmind.runtime import create_runtime
from atlasmind.settings import load_settings


async def run(faq_file: Path, questions_file: Path, report_file: Path) -> None:
    settings = load_settings()
    runtime = create_runtime(settings)
    if not runtime.model_capabilities_configured:
        raise RuntimeError("Configure both model capabilities before real acceptance")
    imported, checks = [], []
    try:
        async with httpx.AsyncClient(timeout=15) as api:
            documents = (await api.get("http://api:8000/v1/documents")).json()["items"]
            for item in json.loads(faq_file.read_text(encoding="utf-8-sig")):
                source = f"yifulu-mvp/common-service/{item['id']}"
                existing = next((d for d in documents if d["sourceKey"] == source), None)
                if existing and existing["activeVersionId"]:
                    imported.append({"title": item["title"], "document_id": existing["id"]})
                    continue
                content = item["content"].encode()
                response = await api.post(
                    "http://api:8000/v1/documents",
                    data={
                        "title": item["title"],
                        "sourceKey": source,
                        "knowledgeScopeCodes": "scope-customer-service",
                        "metadata": json.dumps({"classification": "PUBLIC"}),
                    },
                    files={"file": (f"faq-{item['id']}.txt", content, "text/plain")},
                    headers={"Idempotency-Key": source + ":" + sha256(content).hexdigest()},
                )
                response.raise_for_status()
                accepted = response.json()
                # Reusing the idempotency key returns the original failed job. Retry only
                # this explicit one-time import after its configuration has been corrected.
                if accepted["ingestionJob"]["state"] == "FAILED":
                    retried = await api.post(
                        "http://api:8000/v1/ingestion-jobs/"
                        + accepted["ingestionJob"]["id"]
                        + "/retry"
                    )
                    retried.raise_for_status()
                deadline = monotonic() + 240
                while True:
                    job = (
                        await api.get(
                            "http://api:8000/v1/ingestion-jobs/" + accepted["ingestionJob"]["id"]
                        )
                    ).json()
                    if job["state"] == "SEARCHABLE":
                        break
                    if job["state"] in {"FAILED", "CANCELLED"} or monotonic() >= deadline:
                        raise RuntimeError("FAQ ingestion failed: " + str(job.get("failure")))
                    await asyncio.sleep(1)
                imported.append({"title": item["title"], "document_id": accepted["document"]["id"]})
                print(json.dumps({"imported": item["title"]}, ensure_ascii=False), flush=True)
            for index, line in enumerate(questions_file.read_text(encoding="utf-8").splitlines()):
                question = json.loads(line)
                now = int(time())
                token = jwt.encode(
                    {
                        "iss": "yifulu-service",
                        "aud": "atlasmind-knowledge",
                        "sub": "hq-draft",
                        "iat": now,
                        "nbf": now,
                        "exp": now + 60,
                        "merchant_id": 1,
                        "run_id": index + 1,
                    },
                    settings.service_jwt_secret.get_secret_value(),
                    algorithm="HS256",
                )
                headers = {"Authorization": "Bearer " + token}
                started = monotonic()
                response = await api.post(
                    "http://knowledge-service:8001/v1/knowledge/search",
                    json={"query": question["query"]},
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
                rows = result["data"]
                evidence = {r["chunk_id"]: r["content"] for r in rows}
                answer = await runtime.ai.answer(question["query"], evidence)
                citations = [
                    {k: r[k] for k in ("document_id", "version_id", "chunk_id", "digest")}
                    for r in rows
                    if r["chunk_id"] in answer.citation_ids
                ]
                # Refresh the short-lived service credential after answer generation.
                now = int(time())
                claims = jwt.decode(token, options={"verify_signature": False})
                claims.update(iat=now, nbf=now, exp=now + 30)
                headers["Authorization"] = "Bearer " + jwt.encode(
                    claims, settings.service_jwt_secret.get_secret_value(), algorithm="HS256"
                )
                valid = False
                if citations:
                    checked = await api.post(
                        "http://knowledge-service:8001/v1/knowledge/validate",
                        json={"citations": citations},
                        headers=headers,
                    )
                    checked.raise_for_status()
                    valid = checked.json()["valid"]
                titles = [r["title"] for r in rows if r["chunk_id"] in answer.citation_ids]
                check = {
                    "query": question["query"],
                    "answer": answer.answer,
                    "titles": titles,
                    "passed": bool(valid and question["title"] in titles),
                    "seconds": round(monotonic() - started, 2),
                    "warnings": result["warnings"],
                }
                checks.append(check)
                report_file.write_text(
                    json.dumps(
                        {"imported": imported, "checks": checks}, ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8",
                )
                print(json.dumps(check, ensure_ascii=False), flush=True)
        if not all(c["passed"] for c in checks) or len(checks) != 15:
            raise RuntimeError("Representative question gate failed; inspect the saved report")
    finally:
        await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faq", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.faq, args.questions, args.report))


if __name__ == "__main__":
    main()
