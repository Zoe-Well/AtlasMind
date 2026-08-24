"""Upload validation before any file is accepted into the ingestion workflow."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath


class UploadRejected(ValueError):
    """Stable, non-sensitive upload rejection."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ValidatedFile:
    file_name: str
    media_type: str
    size_bytes: int
    content_digest: str
    object_key: str


class FileValidator:
    supported_types = frozenset(
        {
            "text/plain",
            "text/markdown",
            "text/html",
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    )

    def __init__(self, *, max_file_bytes: int = 50 * 1024 * 1024) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max file bytes must be positive")
        self.max_file_bytes = max_file_bytes

    def validate(self, file_name: str, media_type: str, content: bytes) -> ValidatedFile:
        safe_name = PurePath(file_name).name
        if not safe_name or safe_name in {".", ".."}:
            raise UploadRejected("INVALID_FILE_NAME")
        if media_type not in self.supported_types:
            raise UploadRejected("UNSUPPORTED_MEDIA_TYPE")
        if not content:
            raise UploadRejected("EMPTY_FILE")
        if len(content) > self.max_file_bytes:
            raise UploadRejected("FILE_TOO_LARGE")
        if media_type == "application/pdf" and b"/Encrypt" in content[:1_000_000]:
            raise UploadRejected("ENCRYPTED_FILE")
        digest = f"sha256:{sha256(content).hexdigest()}"
        suffix = PurePath(safe_name).suffix.casefold().removeprefix(".") or "bin"
        return ValidatedFile(
            file_name=safe_name,
            media_type=media_type,
            size_bytes=len(content),
            content_digest=digest,
            object_key=f"knowledge/{digest.removeprefix('sha256:')}.{suffix}",
        )
