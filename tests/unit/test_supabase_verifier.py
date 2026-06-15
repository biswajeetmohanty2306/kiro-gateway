# -*- coding: utf-8 -*-

"""
Unit tests for the Phase C JWT verifier (kiro/supabase_auth/verifier.py, M2).

Covers the happy path plus the review's named negative/security cases:
alg-confusion (none / HS-against-public-key / alg outside set), forged iss,
wrong aud, expiry-with-leeway, far-future iat, bad signature, missing/empty
sub, missing kid, and key-type mismatch.
"""

import time

import jwt
import pytest

from kiro.supabase_auth.verifier import JwtVerifier, VerifiedClaims
from kiro.supabase_auth.jwks_cache import JwksCache
from kiro.supabase_auth.exceptions import (
    InvalidTokenError,
    TokenExpiredError,
    JwksUnavailableError,
)

from _supabase_jwt_helpers import (
    ECKey, RSAKey, FakeConfig, FakeHttpClient, valid_claims, JWKS_URL, AUD, ISS,
)


def build_verifier(client, *, leeway=60, time_fn=None):
    config = FakeConfig(leeway=leeway)
    cache = JwksCache(JWKS_URL, client, ttl_seconds=600)
    kwargs = {}
    if time_fn is not None:
        kwargs["time_fn"] = time_fn
    return JwtVerifier(config, cache, **kwargs)


@pytest.fixture
def ec_key():
    return ECKey("kid-1")


@pytest.fixture
def client_with(ec_key):
    client = FakeHttpClient()
    client.set_keys(ec_key)
    return client


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_valid_token_verifies(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        token = ec_key.sign(valid_claims())

        result = await verifier.verify(token)
        assert isinstance(result, VerifiedClaims)
        assert result.sub == "11111111-1111-1111-1111-111111111111"
        assert result.aud == AUD
        assert result.iss == ISS
        assert result.email == "user@example.com"
        assert result.app_metadata["provider"] == "google"

    @pytest.mark.asyncio
    async def test_verified_claims_is_immutable(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        result = await verifier.verify(ec_key.sign(valid_claims()))
        with pytest.raises(Exception):
            result.sub = "tampered"  # frozen dataclass
        with pytest.raises(Exception):
            result.user_metadata["name"] = "x"  # read-only mapping

    @pytest.mark.asyncio
    async def test_expired_within_leeway_passes(self, ec_key, client_with):
        verifier = build_verifier(client_with, leeway=60)
        now = int(time.time())
        token = ec_key.sign(valid_claims(exp=now - 30))  # 30s past, within 60s leeway
        result = await verifier.verify(token)
        assert result.sub

    @pytest.mark.asyncio
    async def test_missing_optional_email_ok(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        claims = valid_claims()
        del claims["email"]
        result = await verifier.verify(ec_key.sign(claims))
        assert result.email is None


class TestAlgConfusion:
    @pytest.mark.asyncio
    async def test_alg_none_rejected(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        # Craft an unsigned alg=none token.
        token = jwt.encode(
            valid_claims(), key=None, algorithm="none", headers={"kid": "kid-1"}
        )
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)

    @pytest.mark.asyncio
    async def test_hs256_against_public_key_rejected(self, ec_key, client_with):
        """
        Classic confusion: attacker signs HS256 using the public JWK material as
        the HMAC secret. alg HS256 is not in the asymmetric set -> rejected at
        the pre-check, before any key use.
        """
        verifier = build_verifier(client_with)
        pub_jwk = ec_key.public_jwk()
        forged = jwt.encode(
            valid_claims(), key=str(pub_jwk), algorithm="HS256",
            headers={"kid": "kid-1"},
        )
        with pytest.raises(InvalidTokenError):
            await verifier.verify(forged)

    @pytest.mark.asyncio
    async def test_unknown_alg_rejected(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        # ES384 is not in {ES256, RS256}; sign with a matching-curve trick is
        # unnecessary — header alg pre-check rejects it first. Build a token whose
        # header claims ES384 by re-encoding header is complex; instead assert the
        # pre-check via a token actually signed ES256 but we tighten the set.
        # Simpler: a token with HS384 header.
        forged = jwt.encode(
            valid_claims(), key="secret", algorithm="HS384", headers={"kid": "kid-1"}
        )
        with pytest.raises(InvalidTokenError):
            await verifier.verify(forged)


class TestClaimValidation:
    @pytest.mark.asyncio
    async def test_forged_iss_rejected_and_url_unchanged(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        token = ec_key.sign(valid_claims(iss="https://evil.example/auth/v1"))
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)
        # S2: key fetch still went only to the configured URL.
        assert client_with.last_url == JWKS_URL

    @pytest.mark.asyncio
    async def test_wrong_aud_rejected(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        token = ec_key.sign(valid_claims(aud="some-other-audience"))
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)

    @pytest.mark.asyncio
    async def test_expired_beyond_leeway_is_token_expired(self, ec_key, client_with):
        verifier = build_verifier(client_with, leeway=60)
        now = int(time.time())
        token = ec_key.sign(valid_claims(exp=now - 3600))
        with pytest.raises(TokenExpiredError):
            await verifier.verify(token)

    @pytest.mark.asyncio
    async def test_far_future_iat_rejected(self, ec_key, client_with):
        verifier = build_verifier(client_with, leeway=60)
        now = int(time.time())
        token = ec_key.sign(valid_claims(iat=now + 5000, exp=now + 9000))
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)

    @pytest.mark.asyncio
    async def test_bad_signature_rejected(self, client_with):
        """Token signed by a different key than the published JWK."""
        published = ECKey("kid-1")
        attacker = ECKey("kid-1")  # same kid, different key
        client = FakeHttpClient()
        client.set_keys(published)
        verifier = build_verifier(client)

        token = attacker.sign(valid_claims())
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)

    @pytest.mark.asyncio
    async def test_missing_kid_rejected(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        # Sign with kid explicitly cleared from header.
        token = jwt.encode(valid_claims(), ec_key._priv, algorithm="ES256")
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)
        # No network fetch should be needed to reject a kid-less token.
        assert client_with.fetch_count == 0

    @pytest.mark.asyncio
    async def test_empty_sub_rejected(self, ec_key, client_with):
        verifier = build_verifier(client_with)
        token = ec_key.sign(valid_claims(sub=""))
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)

    @pytest.mark.asyncio
    async def test_garbage_token_rejected(self, client_with):
        verifier = build_verifier(client_with)
        with pytest.raises(InvalidTokenError):
            await verifier.verify("not.a.jwt")

    @pytest.mark.asyncio
    async def test_empty_token_rejected(self, client_with):
        verifier = build_verifier(client_with)
        with pytest.raises(InvalidTokenError):
            await verifier.verify("")


class TestKeyTypeMismatch:
    @pytest.mark.asyncio
    async def test_rsa_token_against_only_ec_published(self, client_with, ec_key):
        """An RS256 token whose kid is unknown -> refresh -> still unknown -> invalid."""
        verifier = build_verifier(client_with)
        rsa_key = RSAKey("rsa-kid")
        token = rsa_key.sign(valid_claims())
        with pytest.raises(InvalidTokenError):
            await verifier.verify(token)


class TestTransientPropagation:
    @pytest.mark.asyncio
    async def test_jwks_unavailable_propagates(self, ec_key):
        import httpx
        client = FakeHttpClient()
        client.set_error(httpx.ConnectError("down"))
        verifier = build_verifier(client)
        token = ec_key.sign(valid_claims())
        with pytest.raises(JwksUnavailableError):
            await verifier.verify(token)
