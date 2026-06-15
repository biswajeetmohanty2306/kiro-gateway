# -*- coding: utf-8 -*-

"""
Shared test helpers for Phase C M2 verifier / JWKS cache tests.

Mints real EC P-256 (and one RSA) keypairs in-process, signs tokens with
controlled claims, and serves the matching public JWKs through a fake async
httpx client with a fetch counter. No live Supabase calls.
"""

import json
import time
from typing import Any, Dict, List, Optional

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

ISS = "https://proj.supabase.co/auth/v1"
AUD = "authenticated"
JWKS_URL = "https://proj.supabase.co/auth/v1/.well-known/jwks.json"


class FakeConfig:
    """Minimal stand-in for SupabaseAuthConfig (asymmetric scheme)."""

    def __init__(self, leeway: int = 60):
        self.accepted_algorithms = frozenset({"ES256", "RS256"})
        self.expected_aud = AUD
        self.expected_iss = ISS
        self.jwt_leeway_seconds = leeway
        self.jwks_url = JWKS_URL


class ECKey:
    """An EC P-256 signing key + its public JWK."""

    def __init__(self, kid: str):
        self.kid = kid
        self._priv = ec.generate_private_key(ec.SECP256R1())
        self.alg = "ES256"

    def public_jwk(self) -> Dict[str, Any]:
        jwk = json.loads(ECAlgorithm.to_jwk(self._priv.public_key()))
        jwk["kid"] = self.kid
        jwk["alg"] = "ES256"
        jwk["use"] = "sig"
        return jwk

    def sign(self, claims: Dict[str, Any], *, kid: Optional[str] = None,
             alg: Optional[str] = None) -> str:
        headers = {"kid": kid if kid is not None else self.kid}
        return jwt.encode(claims, self._priv, algorithm=alg or self.alg, headers=headers)


class RSAKey:
    """An RSA signing key + its public JWK (for key-type-mismatch tests)."""

    def __init__(self, kid: str):
        self.kid = kid
        self._priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.alg = "RS256"

    def public_jwk(self) -> Dict[str, Any]:
        jwk = json.loads(RSAAlgorithm.to_jwk(self._priv.public_key()))
        jwk["kid"] = self.kid
        jwk["alg"] = "RS256"
        jwk["use"] = "sig"
        return jwk

    def sign(self, claims: Dict[str, Any], *, kid: Optional[str] = None,
             alg: Optional[str] = None) -> str:
        headers = {"kid": kid if kid is not None else self.kid}
        return jwt.encode(claims, self._priv, algorithm=alg or self.alg, headers=headers)


def valid_claims(**overrides: Any) -> Dict[str, Any]:
    now = int(time.time())
    base = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "aud": AUD,
        "iss": ISS,
        "iat": now,
        "exp": now + 3600,
        "email": "user@example.com",
        "app_metadata": {"provider": "google"},
        "user_metadata": {"name": "Test"},
    }
    base.update(overrides)
    return base


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        import httpx
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}", request=None, response=None
            )


class FakeHttpClient:
    """
    Async httpx-like client. Serves a JWKS document; counts GET calls so tests
    can assert single-flight and steady-state (zero-network) behavior.
    """

    def __init__(self):
        self.fetch_count = 0
        self._jwks: Dict[str, Any] = {"keys": []}
        self._error: Optional[Exception] = None
        self._status: int = 200
        self.last_url: Optional[str] = None

    def set_keys(self, *keys) -> None:
        self._jwks = {"keys": [k.public_jwk() for k in keys]}
        self._error = None
        self._status = 200

    def set_raw_document(self, document: Any) -> None:
        self._jwks = document
        self._error = None
        self._status = 200

    def set_error(self, exc: Exception) -> None:
        self._error = exc

    def set_status(self, status: int) -> None:
        self._status = status

    async def get(self, url: str, *args, **kwargs) -> FakeResponse:
        self.fetch_count += 1
        self.last_url = url
        if self._error is not None:
            raise self._error
        return FakeResponse(self._jwks, status_code=self._status)
