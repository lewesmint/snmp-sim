"""JSON formatting helpers for schema files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_OID_ARRAY_PATTERN = re.compile(
    r'"oid": \[\n(?P<body>(?:\s*-?\d+\s*,\n)+\s*-?\d+\s*\n)\s*\]',
    re.MULTILINE,
)


def _collapse_oid_array(match: re.Match[str]) -> str:
    body = match.group("body")
    numbers = re.findall(r"-?\d+", body)
    return f'"oid": [{", ".join(numbers)}]'


def dumps_with_horizontal_oid_lists(
        payload: Any,
        *,
        indent: int = 2,
        sort_keys: bool = False
    ) -> str:
    """Serialize JSON while keeping values for the 'oid' key on a single line."""
    rendered: str = json.dumps(payload, indent=indent, sort_keys=sort_keys)
    return _OID_ARRAY_PATTERN.sub(_collapse_oid_array, rendered)


def write_json_with_horizontal_oid_lists(
    file_path: str | Path,
    payload: Any,
    *,
    indent: int = 2,
    sort_keys: bool = False,
) -> None:
    """Write JSON to file while keeping values for the 'oid' key on a single line."""
    destination = Path(file_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        dumps_with_horizontal_oid_lists(payload, indent=indent, sort_keys=sort_keys),
        encoding="utf-8",
    )
