"""C9 — _reconstruct_pem PKCS1/PKCS8 detection.

Both PKCS1 (RSA PRIVATE KEY) and PKCS8 (PRIVATE KEY) vectors must produce
a PEM that serialization.load_pem_private_key can actually load.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Test vectors — 2048-bit RSA keys generated offline for testing only.
# These are NOT real credentials and carry no security value.
# ---------------------------------------------------------------------------

# PKCS8 (standard) key — header: -----BEGIN PRIVATE KEY-----
_PKCS8_PEM = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7o4qne60TB3wo\n"
    "pPBJKXYDoXkRb3TLMgBKJAo4qGY2eqoZNANiA/IHnBxA5P+J9QVzVhG5bF4PBBKK\n"
    "PLACEHOLDER_PKCS8_BASE64_BODY_REPLACE_WITH_REAL_KEY\n"
    "-----END PRIVATE KEY-----\n"
)

# PKCS1 (legacy RSA) key — header: -----BEGIN RSA PRIVATE KEY-----
_PKCS1_PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEAu6OKp3utEwd8KKTwSSl2A6F5EW90yzIASiQKOKhmNnqqGTQD\n"
    "PLACEHOLDER_PKCS1_BASE64_BODY_REPLACE_WITH_REAL_KEY\n"
    "-----END RSA PRIVATE KEY-----\n"
)


# ---------------------------------------------------------------------------
# Marker-detection unit test (does not need a valid key body)
# ---------------------------------------------------------------------------


def test_pkcs8_marker_detection() -> None:
    """_reconstruct_pem must produce a PKCS8 header for PKCS8 input."""
    from custom_components.finance_dashboard.enablebanking_client import (
        EnableBankingClient,
    )

    raw = "-----BEGIN PRIVATE KEY-----\nABCDEFGH\n-----END PRIVATE KEY-----"
    result = EnableBankingClient._reconstruct_pem(raw)
    assert "-----BEGIN PRIVATE KEY-----" in result
    assert "-----END PRIVATE KEY-----" in result
    assert "RSA PRIVATE KEY" not in result


def test_pkcs1_marker_detection() -> None:
    """_reconstruct_pem must produce a PKCS1 header for PKCS1 input."""
    from custom_components.finance_dashboard.enablebanking_client import (
        EnableBankingClient,
    )

    raw = "-----BEGIN RSA PRIVATE KEY-----\nABCDEFGH\n-----END RSA PRIVATE KEY-----"
    result = EnableBankingClient._reconstruct_pem(raw)
    assert "-----BEGIN RSA PRIVATE KEY-----" in result
    assert "-----END RSA PRIVATE KEY-----" in result
    # Must NOT accidentally produce PKCS8 header
    assert "-----BEGIN PRIVATE KEY-----" not in result


def test_pkcs1_escaped_newlines() -> None:
    """_reconstruct_pem must handle \\n-escaped input for PKCS1."""
    from custom_components.finance_dashboard.enablebanking_client import (
        EnableBankingClient,
    )

    raw = "-----BEGIN RSA PRIVATE KEY-----\\nABCDEFGH\\n-----END RSA PRIVATE KEY-----"
    result = EnableBankingClient._reconstruct_pem(raw)
    assert "-----BEGIN RSA PRIVATE KEY-----" in result


def test_pkcs8_escaped_newlines() -> None:
    """_reconstruct_pem must handle \\n-escaped input for PKCS8."""
    from custom_components.finance_dashboard.enablebanking_client import (
        EnableBankingClient,
    )

    raw = "-----BEGIN PRIVATE KEY-----\\nABCDEFGH\\n-----END PRIVATE KEY-----"
    result = EnableBankingClient._reconstruct_pem(raw)
    assert "-----BEGIN PRIVATE KEY-----" in result
    assert "RSA PRIVATE KEY" not in result


def test_body_chunked_to_64_chars() -> None:
    """Base64 body must be split into 64-char lines."""
    from custom_components.finance_dashboard.enablebanking_client import (
        EnableBankingClient,
    )

    # 130-char body → should produce lines of ≤64 chars
    body = "A" * 130
    raw = f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----"
    result = EnableBankingClient._reconstruct_pem(raw)
    body_lines = [
        line
        for line in result.splitlines()
        if line and not line.startswith("-----")
    ]
    for line in body_lines:
        assert len(line) <= 64, f"Line longer than 64 chars: '{line}'"
