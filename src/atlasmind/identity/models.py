"""Identity and authorization domain values."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class PrincipalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class Action(StrEnum):
    DISCOVER = "knowledge:discover"
    READ = "knowledge:read"
    CITE = "knowledge:cite"
    MANAGE = "knowledge:manage"
    AUDIT = "operations:audit"


@dataclass(frozen=True, slots=True)
class Principal:
    id: str
    issuer: str
    subject: str
    status: PrincipalStatus = PrincipalStatus.ACTIVE
    authz_revision: int = 1


@dataclass(frozen=True, slots=True)
class Role:
    id: str
    code: str
    name: str
    active: bool = True


@dataclass(frozen=True, slots=True)
class KnowledgeScope:
    id: str
    code: str
    classification: str
    policy_revision: int = 1
    active: bool = True


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    principal_id: str
    role_id: str
    valid_from: datetime
    valid_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class ScopeGrant:
    subject_id: str
    scope_id: str
    actions: frozenset[Action] = field(default_factory=frozenset)
    revision: int = 1


@dataclass(frozen=True, slots=True)
class AuthorizationSnapshot:
    revision: int
    active_scope_ids: frozenset[str]
