"""Tests for startup validation of JWT secret and Apple private key.

Covers:
- _validate_secret_key() rejects keys shorter than 32 bytes (SEC-03)
- _validate_secret_key() accepts keys of 32+ bytes
- _validate_apple_key_if_set() does nothing when APPLE_PRIVATE_KEY unset
- _validate_apple_key_if_set() rejects invalid key material
- _validate_apple_key_if_set() accepts valid PEM and base64-encoded PEM
- Module-level validation runs at import time
"""

import base64
import os
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)


# ---------------------------------------------------------------------------
# Generate a valid ES256 test key fixture
# ---------------------------------------------------------------------------
_test_ec_key = ec.generate_private_key(ec.SECP256R1())
_test_ec_pem = _test_ec_key.private_bytes(
    Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
).decode("utf-8")
_test_ec_pem_b64 = base64.b64encode(_test_ec_pem.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# Secret key validation tests
# ---------------------------------------------------------------------------

class TestValidateSecretKey:
    """Tests for _validate_secret_key()."""

    def test_rejects_short_key(self):
        """Keys shorter than 32 bytes raise RuntimeError."""
        from app.auth.config import _validate_secret_key
        with pytest.raises(RuntimeError, match="too short"):
            _validate_secret_key("short")

    def test_rejects_key_with_31_bytes(self):
        """Keys of exactly 31 bytes are rejected."""
        from app.auth.config import _validate_secret_key
        with pytest.raises(RuntimeError, match="32 bytes"):
            _validate_secret_key("a" * 31)

    def test_accepts_32_byte_key(self):
        """Keys of exactly 32 bytes are accepted."""
        from app.auth.config import _validate_secret_key
        result = _validate_secret_key("a" * 32)
        assert result == "a" * 32

    def test_accepts_64_byte_key(self):
        """Keys longer than 32 bytes are accepted."""
        from app.auth.config import _validate_secret_key
        result = _validate_secret_key("a" * 64)
        assert result == "a" * 64

    def test_error_message_includes_generation_hint(self):
        """Error message includes key generation command."""
        from app.auth.config import _validate_secret_key
        with pytest.raises(RuntimeError, match="secrets.token_urlsafe"):
            _validate_secret_key("short")


# ---------------------------------------------------------------------------
# Apple key validation tests
# ---------------------------------------------------------------------------

class TestValidateAppleKeyIfSet:
    """Tests for _validate_apple_key_if_set()."""

    def test_does_nothing_when_unset(self):
        """No error when APPLE_PRIVATE_KEY is not set."""
        from app.auth.config import _validate_apple_key_if_set
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPLE_PRIVATE_KEY", None)
            _validate_apple_key_if_set()  # should not raise

    def test_does_nothing_when_empty(self):
        """No error when APPLE_PRIVATE_KEY is empty string."""
        from app.auth.config import _validate_apple_key_if_set
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY": ""}):
            _validate_apple_key_if_set()  # should not raise

    def test_rejects_invalid_key(self):
        """Invalid key material raises RuntimeError."""
        from app.auth.config import _validate_apple_key_if_set
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY": "not-a-key"}):
            with pytest.raises(RuntimeError, match="APPLE_PRIVATE_KEY"):
                _validate_apple_key_if_set()

    def test_accepts_valid_pem_key(self):
        """Valid ES256 PEM key is accepted."""
        from app.auth.config import _validate_apple_key_if_set
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY": _test_ec_pem}):
            _validate_apple_key_if_set()  # should not raise

    def test_accepts_base64_encoded_pem_key(self):
        """Base64-encoded ES256 PEM key is accepted."""
        from app.auth.config import _validate_apple_key_if_set
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY": _test_ec_pem_b64}):
            _validate_apple_key_if_set()  # should not raise

    def test_rejects_invalid_base64(self):
        """Invalid base64 that doesn't decode to PEM raises RuntimeError."""
        from app.auth.config import _validate_apple_key_if_set
        # Valid base64 but not a PEM key
        bad_b64 = base64.b64encode(b"not a pem key at all").decode()
        with patch.dict(os.environ, {"APPLE_PRIVATE_KEY": bad_b64}):
            with pytest.raises(RuntimeError, match="APPLE_PRIVATE_KEY"):
                _validate_apple_key_if_set()


# ---------------------------------------------------------------------------
# Module-level integration test
# ---------------------------------------------------------------------------

class TestModuleLevelValidation:
    """Tests that module-level SECRET_KEY assignment calls validation."""

    def test_module_secret_key_is_validated(self):
        """The module-level SECRET_KEY was validated (it exists and is 32+ bytes)."""
        from app.auth.config import SECRET_KEY
        assert len(SECRET_KEY.encode("utf-8")) >= 32
