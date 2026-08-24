"""Enterprise OIDC verification with a strict issuer allowlist."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import jwt

from atlasmind.domain.common import AuthenticationRequired


class OIDCVerifier:
    def __init__(
        self,
        *,
        issuers: Mapping[str, str],
        audience: str,
        algorithms: tuple[str, ...] = ("RS256",),
    ) -> None:
        if not issuers:
            raise ValueError("at least one trusted issuer is required")
        self._issuers = dict(issuers)
        self._audience = audience
        self._algorithms = algorithms

    def verify(self, token: str) -> dict[str, Any]:
        """Verify signature and registered claims before subject mapping."""
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            issuer = str(unverified.get("iss", ""))
            key = self._issuers.get(issuer)
            if key is None:
                raise AuthenticationRequired(details={"reason": "OIDC_ISSUER_NOT_ALLOWED"})
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=issuer,
                options={"require": ["iss", "sub", "aud", "iat", "exp"]},
            )
            if not str(claims["sub"]).strip():
                raise AuthenticationRequired(details={"reason": "OIDC_SUBJECT_INVALID"})
            return dict(claims)
        except AuthenticationRequired:
            raise
        except jwt.PyJWTError as exc:
            raise AuthenticationRequired(details={"reason": "OIDC_TOKEN_INVALID"}) from exc
