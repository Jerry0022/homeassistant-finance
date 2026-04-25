"""Tests for JWT generation via PyJWT (A4).

Verifies that EnableBankingClient._generate_jwt produces a valid RS256-signed
token with the correct claims and 60-second TTL.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def _generate_test_key_pair():
    """Generate a fresh RSA-2048 key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_key = private_key.public_key()
    return private_pem, public_key


APPLICATION_ID = "test-app-id-12345"


def _make_client(private_pem: str):
    from custom_components.finance_dashboard.enablebanking_client import (
        EnableBankingClient,
    )
    return EnableBankingClient(
        application_id=APPLICATION_ID,
        private_key_pem=private_pem,
    )


class TestJwtGeneration:
    """JWT generation tests for EnableBankingClient."""

    def test_jwt_is_decodable_with_public_key(self):
        """Generated token must be verifiable with the matching public key."""
        private_pem, public_key = _generate_test_key_pair()
        client = _make_client(private_pem)
        token = client._generate_jwt()

        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="api.tilisy.com",
        )
        assert decoded is not None

    def test_jwt_iss_is_application_id(self):
        """iss claim must equal the application_id (not 'enablebanking.com')."""
        private_pem, public_key = _generate_test_key_pair()
        client = _make_client(private_pem)
        token = client._generate_jwt()

        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="api.tilisy.com",
        )
        assert decoded["iss"] == APPLICATION_ID

    def test_jwt_aud_is_tilisy(self):
        """aud claim must be 'api.tilisy.com'."""
        private_pem, public_key = _generate_test_key_pair()
        client = _make_client(private_pem)
        token = client._generate_jwt()

        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="api.tilisy.com",
        )
        assert decoded["aud"] == "api.tilisy.com"

    def test_jwt_ttl_is_60_seconds(self):
        """exp - iat must be exactly 60 seconds."""
        private_pem, public_key = _generate_test_key_pair()
        client = _make_client(private_pem)

        before = int(time.time())
        token = client._generate_jwt()
        after = int(time.time())

        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="api.tilisy.com",
        )
        ttl = decoded["exp"] - decoded["iat"]
        assert ttl == 60
        # iat must be within [before, after+1] (clock tolerance)
        assert before <= decoded["iat"] <= after + 1

    def test_jwt_has_jti_claim(self):
        """jti claim must be present and non-empty (replay protection)."""
        private_pem, public_key = _generate_test_key_pair()
        client = _make_client(private_pem)
        token = client._generate_jwt()

        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="api.tilisy.com",
        )
        assert "jti" in decoded
        assert len(decoded["jti"]) >= 16

    def test_jwt_jti_unique_per_call(self):
        """Each call must produce a different jti (no token reuse)."""
        private_pem, public_key = _generate_test_key_pair()
        client = _make_client(private_pem)

        tokens = [client._generate_jwt() for _ in range(5)]
        jtis = set()
        for token in tokens:
            decoded = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="api.tilisy.com",
            )
            jtis.add(decoded["jti"])

        assert len(jtis) == 5, "All jti values must be unique"

    def test_jwt_header_contains_kid(self):
        """JWT header must carry kid = application_id."""
        private_pem, _ = _generate_test_key_pair()
        client = _make_client(private_pem)
        token = client._generate_jwt()

        header = jwt.get_unverified_header(token)
        assert header["kid"] == APPLICATION_ID
        assert header["alg"] == "RS256"

    def test_jwt_algorithm_is_rs256(self):
        """Algorithm header must be RS256."""
        private_pem, _ = _generate_test_key_pair()
        client = _make_client(private_pem)
        token = client._generate_jwt()

        header = jwt.get_unverified_header(token)
        assert header["alg"] == "RS256"

    # -----------------------------------------------------------------------
    # T3 edge-cases
    # -----------------------------------------------------------------------

    def test_jwt_rejected_for_wrong_algorithm(self):
        """PyJWT must reject a token when the caller insists on HS256 only.

        RS256-signed tokens must NOT verify under HS256 — this guards against
        algorithm-confusion attacks where an attacker downgrades to HMAC.
        """
        private_pem, _ = _generate_test_key_pair()
        client = _make_client(private_pem)
        token = client._generate_jwt()

        # Decoding as HS256 must raise DecodeError or InvalidAlgorithmError
        with pytest.raises(jwt.exceptions.PyJWTError):
            jwt.decode(
                token,
                "any-secret",
                algorithms=["HS256"],
                audience="api.tilisy.com",
            )

    def test_jwt_rejected_when_expired(self):
        """A token whose exp is in the past must be rejected by PyJWT."""
        import time as _time

        private_pem, public_key = _generate_test_key_pair()
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        from cryptography.hazmat.primitives import serialization as _ser

        # Build a payload that expired 120 seconds ago
        now = int(_time.time())
        payload = {
            "iss": APPLICATION_ID,
            "aud": "api.tilisy.com",
            "iat": now - 180,
            "exp": now - 120,  # already expired
            "jti": "test-expired-jti",
        }
        private_key = _ser.load_pem_private_key(
            private_pem.encode(), password=None
        )
        expired_token = jwt.encode(
            payload, private_key, algorithm="RS256",
            headers={"kid": APPLICATION_ID},
        )

        with pytest.raises(jwt.exceptions.ExpiredSignatureError):
            jwt.decode(
                expired_token,
                public_key,
                algorithms=["RS256"],
                audience="api.tilisy.com",
            )

    def test_jwt_iat_within_one_second_of_now(self):
        """iat claim must not be in the future (clock-skew guard).

        If the system clock is correct, iat should never exceed now + 1s.
        A future iat would mean the JWT is valid from some future point and
        breaks replay-protection assumptions.
        """
        private_pem, public_key = _generate_test_key_pair()
        client = _make_client(private_pem)

        before = int(time.time())
        token = client._generate_jwt()
        after = int(time.time()) + 1  # +1 for sub-second tolerance

        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="api.tilisy.com",
        )
        # iat must be in the window [before, after]
        assert before <= decoded["iat"] <= after, (
            f"iat={decoded['iat']} outside [{before}, {after}]"
        )

    def test_jwt_different_keys_produce_invalid_signature(self):
        """Token signed by key A must NOT verify against key B's public key."""
        private_pem_a, _ = _generate_test_key_pair()
        _, public_key_b = _generate_test_key_pair()

        client = _make_client(private_pem_a)
        token = client._generate_jwt()

        with pytest.raises(jwt.exceptions.PyJWTError):
            jwt.decode(
                token,
                public_key_b,
                algorithms=["RS256"],
                audience="api.tilisy.com",
            )
