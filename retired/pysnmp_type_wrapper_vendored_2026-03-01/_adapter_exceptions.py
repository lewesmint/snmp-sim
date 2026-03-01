"""Shared exception tuple for reflection-heavy adapter boundaries."""

from __future__ import annotations

ADAPTER_EXCEPTIONS = (
    AttributeError,
    LookupError,
    OSError,
    TypeError,
    ValueError,
    RuntimeError,
)
