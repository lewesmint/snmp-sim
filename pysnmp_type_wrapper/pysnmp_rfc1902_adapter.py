"""Boundary adapter for dynamic ``pysnmp.proto.rfc1902`` access."""

from __future__ import annotations

ADAPTER_EXCEPTIONS = (
    AttributeError,
    LookupError,
    OSError,
    TypeError,
    ValueError,
    RuntimeError,
)


class PysnmpRfc1902Adapter:
    """Wrap dynamic module reflection behind typed helper methods."""

    def __init__(self, rfc1902_module: object) -> None:
        """Bind adapter to a concrete `pysnmp.proto.rfc1902`-like module object."""
        self._module = rfc1902_module

    def get_symbol(self, name: str) -> object | None:
        """Return named symbol from module when available."""
        try:
            return getattr(self._module, name, None)
        except ADAPTER_EXCEPTIONS:
            return None

    def iter_public_symbols(self) -> list[tuple[str, object]]:
        """Return public symbol name/object pairs from the module."""
        try:
            names = dir(self._module)
        except ADAPTER_EXCEPTIONS:
            return []

        out: list[tuple[str, object]] = []
        for name in names:
            if name.startswith("_"):
                continue
            obj = self.get_symbol(name)
            if obj is None:
                continue
            out.append((name, obj))
        return out

    @staticmethod
    def has_attribute(obj: object, attr_name: str) -> bool:
        """Return whether object exposes named attribute."""
        try:
            getattr(obj, attr_name)
        except ADAPTER_EXCEPTIONS:
            return False
        else:
            return True
