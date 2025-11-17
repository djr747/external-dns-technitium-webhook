"""Tests for logging_utils module."""

import json
import logging

from external_dns_technitium_webhook.logging_utils import (
    _redact_dict,
    _sanitize_value,
    safe_log_payload,
    safe_log_request_headers,
    safe_serialize_payload,
)


class TestSanitizeValue:
    """Test _sanitize_value function."""

    def test_sanitize_value_none(self):
        """Test that None returns None."""
        assert _sanitize_value(None) is None

    def test_sanitize_value_normal_string(self):
        """Test normal string is returned unchanged."""
        result = _sanitize_value("hello world")
        assert result == "hello world"

    def test_sanitize_value_removes_control_chars(self):
        """Test control characters are removed."""
        # Include null byte and other control chars
        result = _sanitize_value("hello\x00world\x1ftest")
        assert result is not None
        assert "\x00" not in result
        assert "\x1f" not in result
        assert "hello" in result and "world" in result and "test" in result

    def test_sanitize_value_removes_newlines(self):
        """Test newlines and carriage returns are removed."""
        result = _sanitize_value("hello\nworld\rtest")
        assert result is not None
        assert "\n" not in result
        assert "\r" not in result

    def test_sanitize_value_truncates_long_string(self):
        """Test long strings are truncated."""
        long_string = "a" * 300
        result = _sanitize_value(long_string, max_len=256)
        assert result is not None
        assert len(result) == 256 + len("...(truncated)")
        assert result.endswith("...(truncated)")

    def test_sanitize_value_custom_max_len(self):
        """Test custom max_len parameter."""
        long_string = "a" * 100
        result = _sanitize_value(long_string, max_len=50)
        assert result is not None
        assert len(result) == 50 + len("...(truncated)")


class TestRedactDict:
    """Test _redact_dict function."""

    def test_redact_dict_simple_password(self):
        """Test simple password redaction."""
        obj = {"username": "admin", "password": "secret123"}
        result = _redact_dict(obj, ("password",))
        assert isinstance(result, dict)
        assert result["username"] == "admin"
        assert result["password"] == "<redacted>"

    def test_redact_dict_case_insensitive(self):
        """Test redaction is case-insensitive."""
        obj = {"PASSWORD": "secret", "api_KEY": "token"}
        result = _redact_dict(obj, ("password", "api_key"))
        assert isinstance(result, dict)
        assert result["PASSWORD"] == "<redacted>"
        assert result["api_KEY"] == "<redacted>"

    def test_redact_dict_nested(self):
        """Test redaction in nested dicts."""
        obj = {
            "user": {"name": "admin", "password": "secret"},
            "api_config": {"token": "abc123", "url": "https://example.com"},
        }
        result = _redact_dict(obj, ("password", "token"))
        assert isinstance(result, dict)
        user_result = result["user"]
        assert isinstance(user_result, dict)
        assert user_result["password"] == "<redacted>"
        api_result = result["api_config"]
        assert isinstance(api_result, dict)
        assert api_result["token"] == "<redacted>"
        assert user_result["name"] == "admin"

    def test_redact_dict_with_lists(self):
        """Test redaction in dicts containing lists."""
        obj = {
            "items": [{"password": "secret1"}, {"password": "secret2"}],
            "config": {"api_key": "token123"},
        }
        result = _redact_dict(obj, ("password", "api_key"))
        assert isinstance(result, dict)
        items = result["items"]
        assert isinstance(items, list)
        assert isinstance(items[0], dict)
        assert items[0]["password"] == "<redacted>"
        assert items[1]["password"] == "<redacted>"
        config = result["config"]
        assert isinstance(config, dict)
        assert config["api_key"] == "<redacted>"

    def test_redact_dict_non_dict_unchanged(self):
        """Test that non-dict values are unchanged."""
        result = _redact_dict("string", ("key",))
        assert result == "string"
        result = _redact_dict(123, ("key",))
        assert result == 123

    def test_redact_dict_list_passthrough(self):
        """Test list at top level."""
        obj = [{"password": "secret"}, "string", 123]
        result = _redact_dict(obj, ("password",))
        assert isinstance(result, list)
        assert isinstance(result[0], dict)
        assert result[0]["password"] == "<redacted>"
        assert result[1] == "string"
        assert result[2] == 123


class TestSafeSerializePayload:
    """Test safe_serialize_payload function."""

    def test_serialize_simple_dict(self):
        """Test serialization of simple dict."""
        obj = {"key": "value", "number": 42}
        result = safe_serialize_payload(obj)
        parsed = json.loads(result)
        assert parsed["key"] == "value"
        assert parsed["number"] == 42

    def test_serialize_redacts_password(self):
        """Test that password is redacted by default."""
        obj = {"username": "admin", "password": "secret123"}
        result = safe_serialize_payload(obj)
        parsed = json.loads(result)
        assert parsed["password"] == "<redacted>"

    def test_serialize_redacts_token(self):
        """Test that token is redacted by default."""
        obj = {"api_token": "abc123def456"}
        result = safe_serialize_payload(obj)
        parsed = json.loads(result)
        assert parsed["api_token"] == "<redacted>"

    def test_serialize_custom_redact_keys(self):
        """Test custom redact_keys."""
        obj = {"secret_field": "sensitive_value", "public_field": "ok"}
        result = safe_serialize_payload(obj, redact_keys=("secret_field",))
        parsed = json.loads(result)
        assert parsed["secret_field"] == "<redacted>"
        assert parsed["public_field"] == "ok"

    def test_serialize_truncates_long_output(self):
        """Test that long output is truncated."""
        obj = {"data": "x" * 5000}
        result = safe_serialize_payload(obj, max_len=100)
        assert len(result) <= 100 + len("...(truncated)")
        assert result.endswith("...(truncated)")

    def test_serialize_handles_invalid_json(self):
        """Test fallback when json.dumps fails."""

        # Create an object that might fail to serialize
        class UnserializableObject:
            def __repr__(self):
                return "UnserializableObject"

        obj = UnserializableObject()
        result = safe_serialize_payload(obj)
        # Should fall back to str()
        assert isinstance(result, str)

    def test_serialize_removes_control_chars(self):
        """Test control characters are removed."""
        obj = {"text": "hello\x00world\ntest"}
        result = safe_serialize_payload(obj)
        assert "\x00" not in result
        assert "\n" not in result


class TestSafeLogRequestHeaders:
    """Test safe_log_request_headers function."""

    def test_log_allowlisted_headers(self, caplog):
        """Test that allowlisted headers are logged."""
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Authorization": "Bearer token123",
        }
        logger = logging.getLogger("test")
        safe_log_request_headers(headers, logger)

        # Authorization should not be logged, but Accept headers should be
        assert "Accept" in caplog.text
        assert "gzip" in caplog.text

    def test_log_default_allowlist(self, caplog):
        """Test default allowlist is used."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "ExternalDNS/1.0",
            "X-Custom-Header": "should-not-appear",
        }
        logger = logging.getLogger("test")
        safe_log_request_headers(headers, logger)

        assert "Accept" in caplog.text
        assert "User-Agent" in caplog.text
        assert "X-Custom-Header" not in caplog.text

    def test_log_custom_allowlist(self, caplog):
        """Test custom allowlist."""
        headers = {
            "Accept": "application/json",
            "X-Custom": "value",
        }
        logger = logging.getLogger("test")
        safe_log_request_headers(headers, logger, allowlist=("x-custom",))

        assert "X-Custom" in caplog.text
        assert "Accept" not in caplog.text

    def test_log_redacted_headers_noted(self, caplog):
        """Test that redacted headers are noted."""
        headers = {
            "Authorization": "Bearer token123",
            "Cookie": "session=abc",
        }
        logger = logging.getLogger("test")
        safe_log_request_headers(headers, logger)

        # Should note that redacted headers are present
        assert "redacted" in caplog.text.lower()

    def test_log_empty_headers(self, caplog):
        """Test logging with empty headers."""
        headers = {}
        logger = logging.getLogger("test")
        safe_log_request_headers(headers, logger)

        # Should log that no headers are present
        assert "no allowlisted headers" in caplog.text

    def test_log_custom_redact_keys(self, caplog):
        """Test custom redact_keys - redaction only applies if header not in allowlist."""
        headers = {
            "Accept": "application/json",
            "Authorization": "Bearer secret",
        }
        logger = logging.getLogger("test")
        # Even though Authorization is custom-redacted, it's not in allowlist so won't appear
        safe_log_request_headers(
            headers,
            logger,
            allowlist=("accept",),
            redact_keys=("authorization",),
        )

        # Accept should be logged but Authorization should be noted as redacted
        assert "Accept" in caplog.text
        assert "redacted" in caplog.text.lower()

    def test_log_header_values_sanitized(self, caplog):
        """Test that header values are sanitized."""
        headers = {"Accept": "application/json\x00\x1fwith-control-chars"}
        logger = logging.getLogger("test")
        safe_log_request_headers(headers, logger)

        # Control characters should be removed
        assert "\x00" not in caplog.text
        assert "\x1f" not in caplog.text


class TestSafeLogPayload:
    """Test safe_log_payload function."""

    def test_log_payload_success(self, caplog):
        """Test successful payload logging."""
        payload = {"key": "value", "number": 42}
        logger = logging.getLogger("test")
        safe_log_payload("test_payload", payload, logger)

        assert "[PAYLOAD]" in caplog.text
        assert "test_payload" in caplog.text
        assert "value" in caplog.text

    def test_log_payload_redacts_sensitive_data(self, caplog):
        """Test payload logging redacts sensitive data."""
        payload = {"username": "admin", "password": "secret123"}
        logger = logging.getLogger("test")
        safe_log_payload("credentials", payload, logger)

        assert "[PAYLOAD]" in caplog.text
        assert "<redacted>" in caplog.text
        assert "secret123" not in caplog.text

    def test_log_payload_custom_level(self, caplog):
        """Test custom log level."""
        payload = {"key": "value"}
        logger = logging.getLogger("test")
        safe_log_payload("test", payload, logger, level=logging.WARNING)

        # The log should appear at WARNING level
        assert any(record.levelname == "WARNING" for record in caplog.records)

    def test_log_payload_handles_exception(self, caplog, mocker):
        """Test graceful handling when serialization fails."""
        # Mock safe_serialize_payload to raise an exception
        mocker.patch(
            "external_dns_technitium_webhook.logging_utils.safe_serialize_payload",
            side_effect=Exception("Serialization failed"),
        )

        payload = {"key": "value"}
        logger = logging.getLogger("test")
        safe_log_payload("bad_payload", payload, logger)

        # Should log failure message instead of raising
        assert "[PAYLOAD]" in caplog.text
        assert "bad_payload" in caplog.text
        assert "<failed to serialize>" in caplog.text
