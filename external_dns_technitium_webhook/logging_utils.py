"""Safe header and payload logging utilities.

This module provides small, focused helpers used by the webhook to emit
concise, safe diagnostic logs without leaking secrets or large payloads.

Public helpers
- ``safe_log_request_headers(headers, logger, *, allowlist=None, redact_keys=None, level=logging.DEBUG)``
    Logs an allowlisted subset of HTTP request headers after sanitizing
    control characters and truncating long values. Headers in
    ``redact_keys`` are noted but not printed. Default allowlist includes
    ``Accept-Encoding``, ``Accept``, ``Content-Encoding``, ``User-Agent``,
    and ``Host``.

- ``safe_serialize_payload(payload, *, redact_keys=None, max_len=4096) -> str``
    Produces a JSON string for logging by redacting keys that look
    sensitive (e.g. ``password``, ``token``, ``authorization``), removing
    control characters and truncating to ``max_len``.

- ``safe_log_payload(name, payload, logger, *, level=logging.DEBUG)``
    Convenience wrapper that serializes a payload with
    ``safe_serialize_payload`` and writes a structured log entry.

Internal helpers
- ``_sanitize_value``: strip control characters and truncate strings.
- ``_redact_dict``: recursively redact mapping keys that match the
    configured sensitive key list.

Usage notes
- These helpers are intentionally conservative: they only emit a small
    amount of diagnostic information and redact known sensitive keys.
- They are suitable for logging incoming request headers and payloads
    from ExternalDNS while avoiding exposure of credentials or large
    bodies. Do not use them as a general-purpose serializer for
    application data where full fidelity is required.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping

# Remove control characters and newlines that could corrupt logs
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\r\n]+")


def _sanitize_value(value: str | None, max_len: int = 256) -> str | None:
    if value is None:
        return None
    # remove control characters
    s = _CONTROL_RE.sub("", value)
    if len(s) > max_len:
        return s[:max_len] + "...(truncated)"
    return s


def safe_log_request_headers(
    headers: Mapping[str, str],
    logger: logging.Logger,
    *,
    allowlist: tuple[str, ...] | None = None,
    redact_keys: tuple[str, ...] | None = None,
    level: int = logging.DEBUG,
) -> None:
    """Log a small, safe summary of request headers.

    - Only allowlisted header names are emitted with sanitized values.
    - Redacted headers are noted but not printed.
    - Control characters are removed and values are truncated.

    This function avoids logging the full header map to reduce the risk
    of sensitive data leakage.
    """
    if allowlist is None:
        allowlist = ("accept-encoding", "accept", "content-encoding", "user-agent", "host")
    if redact_keys is None:
        redact_keys = ("authorization", "cookie", "set-cookie", "proxy-authorization")

    out: dict[str, str] = {}
    present_redacted: list[str] = []

    for k, v in headers.items():
        lk = k.lower()
        if lk in allowlist:
            val = _sanitize_value(v)
            out[k] = val if val is not None else ""
        elif lk in redact_keys:
            present_redacted.append(k)

    if not out and not present_redacted:
        logger.log(level, "[HEADERS] no allowlisted headers present")
        return

    # Build a concise, structured message
    parts: list[str] = []
    for k, v in out.items():
        parts.append(f"{k}={v}")
    if present_redacted:
        parts.append(f"redacted=[{', '.join(present_redacted)}]")

    logger.log(level, "[HEADERS] %s", "; ".join(parts))


def _redact_dict(obj: object, redact_keys: tuple[str, ...]) -> object:
    """Recursively redact values in mappings for keys matching redact_keys.

    Returns a new structure with redacted values; leaves non-mappings unchanged.
    """
    if isinstance(obj, dict):
        out: dict = {}
        for k, v in obj.items():
            lk = k.lower() if isinstance(k, str) else None
            if lk and any(rk in lk for rk in redact_keys):
                out[k] = "<redacted>"
            else:
                out[k] = _redact_dict(v, redact_keys)
        return out
    if isinstance(obj, list):
        return [_redact_dict(v, redact_keys) for v in obj]
    return obj


def safe_serialize_payload(
    payload: object, *, redact_keys: tuple[str, ...] | None = None, max_len: int = 4096
) -> str:
    """Serialize a payload (typically parsed JSON/Pydantic model) for safe logging.

    - Redacts keys matching redact_keys.
    - Truncates the resulting JSON string to max_len.
    - Removes control characters.
    """
    import json

    if redact_keys is None:
        redact_keys = ("password", "token", "api_key", "secret", "authorization", "cookie")

    try:
        redacted = _redact_dict(payload, redact_keys)
        s = json.dumps(redacted, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        # Fallback to string conversion
        s = str(payload)

    s = _CONTROL_RE.sub("", s)
    if len(s) > max_len:
        return s[:max_len] + "...(truncated)"
    return s


def safe_log_payload(
    name: str, payload: object, logger: logging.Logger, *, level: int = logging.DEBUG
) -> None:
    try:
        s = safe_serialize_payload(payload)
        logger.log(level, "[PAYLOAD] %s: %s", name, s)
    except Exception:
        logger.log(level, "[PAYLOAD] %s: <failed to serialize>", name, exc_info=True)
