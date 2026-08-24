"""Immutable object storage port and S3-compatible adapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from hashlib import sha256
from typing import BinaryIO, Protocol

import boto3
from botocore.exceptions import ClientError

from atlasmind.domain.common import InvalidState


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    digest: str
    size_bytes: int
    version_id: str | None


class ObjectStore(Protocol):
    async def put_immutable(self, key: str, body: BinaryIO, *, size_bytes: int) -> StoredObject: ...
    async def get_stream(self, key: str) -> AsyncIterator[bytes]: ...


class S3ObjectStore:
    def __init__(self, *, bucket: str, endpoint_url: str, access_key: str, secret_key: str) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    async def ensure_bucket(self) -> None:
        """Create the configured bucket once for local/S3-compatible deployments."""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            await asyncio.to_thread(self._client.create_bucket, Bucket=self._bucket)

    async def put_immutable(self, key: str, body: BinaryIO, *, size_bytes: int) -> StoredObject:
        data = body.read()
        if len(data) != size_bytes:
            raise ValueError("declared object size does not match body")
        digest = f"sha256:{sha256(data).hexdigest()}"
        try:
            result = self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentLength=size_bytes,
                Metadata={"sha256": digest.removeprefix("sha256:")},
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"PreconditionFailed", "412"}:
                raise InvalidState(details={"reason": "OBJECT_ALREADY_EXISTS"}) from exc
            raise
        return StoredObject(key, digest, size_bytes, result.get("VersionId"))

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        while chunk := await asyncio.to_thread(response["Body"].read, 64 * 1024):
            yield chunk

    async def get_bytes(self, key: str) -> bytes:
        return b"".join([chunk async for chunk in self.get_stream(key)])
