#!/usr/bin/env python3
"""Normalize Snyk SARIF security-severity properties for GitHub ingestion."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _severity_string(value: Any) -> str | None:
    """Return a valid SARIF severity score as a string, or omit it."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None

    source = str(value).strip()
    try:
        score = Decimal(source)
    except InvalidOperation:
        return None

    if not score.is_finite() or score <= 0 or score > 10:
        return None

    return source


def normalize_sarif(value: Any) -> Any:
    """Recursively keep only valid GitHub SARIF severity score strings."""
    if isinstance(value, list):
        return [normalize_sarif(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key == "security-severity":
            severity = _severity_string(item)
            if severity is not None:
                normalized[key] = severity
        else:
            normalized[key] = normalize_sarif(item)
    return normalized


def normalize_file(path: Path) -> bool:
    """Normalize one SARIF file in place; return False when it is absent."""
    if not path.is_file():
        return False

    sarif = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_sarif(sarif)
    temporary_path = path.with_name(f"{path.name}.normalized")
    temporary_path.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="Snyk SARIF report paths")
    args = parser.parse_args()

    for report in args.reports:
        if normalize_file(report):
            print(f"Normalized SARIF severity properties: {report}")


if __name__ == "__main__":
    main()
