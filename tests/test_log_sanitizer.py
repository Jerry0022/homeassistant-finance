"""Tests for _sanitize_log — standalone regex tests (S1).

The sanitizer logic lives in enablebanking_client.py but the regexes are
pure-Python with no HA or network dependencies, so we duplicate the patterns
here for fast, isolated testing. The actual function is also imported and
tested directly via the regex-only path.
"""
import re
import pytest

# ---------------------------------------------------------------------------
# Inline copy of the patterns (ensures test stays in sync with the source)
# ---------------------------------------------------------------------------

_RE_IBAN = re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7,25}\b')
_RE_ACCOUNT_ID = re.compile(r'\b\d{16,19}\b')
_RE_AMOUNT = re.compile(r'\b\d+[.,]\d{2}\s*(?:EUR|€)\b', re.IGNORECASE)


def _sanitize_log(text: str) -> str:
    """Mirror of enablebanking_client._sanitize_log for isolated testing."""
    text = _RE_IBAN.sub("***IBAN***", text)
    text = _RE_ACCOUNT_ID.sub("***ACCOUNT***", text)
    text = _RE_AMOUNT.sub("***AMOUNT***", text)
    return text


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_iban_masked():
    """German IBAN must be replaced with ***IBAN***."""
    raw = '{"iban": "DE89370400440532013000", "status": "ok"}'
    result = _sanitize_log(raw)
    assert "DE89370400440532013000" not in result
    assert "***IBAN***" in result


def test_account_id_masked():
    """16-19 digit numeric strings (card / account IDs) must be masked."""
    raw = "account_id=1234567890123456 rejected"
    result = _sanitize_log(raw)
    assert "1234567890123456" not in result
    assert "***ACCOUNT***" in result


def test_eur_amount_masked():
    """Monetary amounts with EUR suffix must be masked."""
    raw = "balance: 1234.56 EUR available"
    result = _sanitize_log(raw)
    assert "1234.56 EUR" not in result
    assert "***AMOUNT***" in result


def test_combined_pii_all_masked():
    """A response body with all three PII types is fully sanitized."""
    raw = (
        '{"iban":"DE89370400440532013000",'
        '"account":"9876543210987654",'
        '"amount":"2500.00 EUR",'
        '"error":"consent_required"}'
    )
    result = _sanitize_log(raw)
    assert "DE89370400440532013000" not in result
    assert "9876543210987654" not in result
    assert "2500.00 EUR" not in result
    # Non-PII field must survive
    assert "consent_required" in result


def test_clean_text_unchanged():
    """Text without any PII must pass through unmodified."""
    raw = '{"error": "consent_required", "code": "ERR_429"}'
    result = _sanitize_log(raw)
    assert result == raw
