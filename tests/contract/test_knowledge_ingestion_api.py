"""US2 public knowledge-ingestion API contract."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from atlasmind.api.middleware.auth_context import AuthContext
from atlasmind.api.routes.documents import create_document_router
from atlasmind.api.routes.ingestion_jobs import create_ingestion_job_router
from atlasmind.api.routes.metadata_review import create_metadata_review_router
from atlasmind.application.ingest_document import InMemoryIngestionService
from atlasmind.identity.models import Action


def auth() -> AuthContext:
    now = datetime.now(UTC)
    return AuthContext(
        principal_id="knowledge-admin",
        role_codes=frozenset({"knowledge-admin"}),
        scope_ids=frozenset({"scope-public"}),
        allowed_actions=frozenset({Action.READ, Action.CITE, Action.MANAGE}),
        authz_revision=1,
        policy_revision=1,
        correlation_id="00000000-0000-0000-0000-000000000001",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def app(service: InMemoryIngestionService) -> FastAPI:
    api = FastAPI()
    api.include_router(create_document_router(service, auth))
    api.include_router(create_ingestion_job_router(service, auth))
    api.include_router(create_metadata_review_router(service, auth))
    return api


@pytest.mark.asyncio
@pytest.mark.contract
async def test_upload_read_version_revoke_and_job_contract() -> None:
    service = InMemoryIngestionService()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app(service)), base_url="http://test"
    ) as api:
        created = await api.post(
            "/v1/documents",
            headers={"Idempotency-Key": "upload-refund-policy-v1"},
            files={
                "file": (
                    "refund.txt",
                    b"Refund requests are accepted for 30 days.",
                    "text/plain",
                )
            },
            data={
                "title": "Refund policy",
                "sourceKey": "policy/refund",
                "knowledgeScopeCodes": "scope-public",
                "metadata": json.dumps({"businessOwner": "Finance", "classification": "INTERNAL"}),
            },
        )

        assert created.status_code == 202
        body = created.json()
        assert body["document"]["status"] == "ACTIVE"
        assert body["document"]["activeVersionId"] is None
        assert body["ingestionJob"]["state"] == "QUEUED"
        assert "objectKey" not in json.dumps(body)

        document_id = body["document"]["id"]
        job_id = body["ingestionJob"]["id"]
        fetched = await api.get(f"/v1/documents/{document_id}")
        assert fetched.status_code == 200
        assert fetched.json()["knowledgeScopes"] == ["scope-public"]

        version = await api.post(
            f"/v1/documents/{document_id}/versions",
            headers={"Idempotency-Key": "upload-refund-policy-v2"},
            files={
                "file": (
                    "refund-v2.txt",
                    b"Refund requests are accepted for 45 days.",
                    "text/plain",
                )
            },
            data={"versionLabel": "v2"},
        )
        assert version.status_code == 202
        version_id = version.json()["versionId"]
        assert version_id != body["versionId"]

        reviewed = await api.post(
            f"/v1/document-versions/{version_id}/metadata-review",
            json={"approved": True, "corrections": {"businessOwner": "Finance Ops"}},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["documentVersionId"] == version_id
        assert reviewed.json()["metadata"]["businessOwner"] == {
            "value": "Finance Ops",
            "status": "CONFIRMED",
        }

        job = await api.get(f"/v1/ingestion-jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["currentStage"] == "VALIDATING"

        retry = await api.post(
            f"/v1/ingestion-jobs/{job_id}/retry",
            headers={"Idempotency-Key": "retry-before-failure"},
        )
        assert retry.status_code == 409

        revoked = await api.delete(f"/v1/documents/{document_id}")
        assert revoked.status_code == 202
        assert revoked.json()["status"] == "REVOKED"


@pytest.mark.asyncio
@pytest.mark.contract
async def test_upload_rejects_authority_fields_and_ungranted_scope() -> None:
    service = InMemoryIngestionService()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app(service)), base_url="http://test"
    ) as api:
        response = await api.post(
            "/v1/documents",
            headers={"Idempotency-Key": "forged-authority"},
            files={"file": ("secret.txt", b"secret", "text/plain")},
            data={
                "title": "Secret",
                "sourceKey": "secret",
                "knowledgeScopeCodes": "scope-secret",
                "principalId": "forged-admin",
            },
        )

    assert response.status_code in {403, 422}
