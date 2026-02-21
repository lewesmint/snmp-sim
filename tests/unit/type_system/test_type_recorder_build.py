import types
from pathlib import Path
from typing import Any

import pytest

from app.type_recorder import TypeRecorder


def make_fake_builder(mib_symbols: dict[str, dict[str, object]]) -> Any:
    class FakeBuilder:
        def __init__(self, symbols: dict[str, dict[str, object]]):
            self.mibSymbols = symbols

        def add_mib_sources(self, src: object) -> None:
            pass

        def load_modules(self, *args: object) -> None:
            pass

    return FakeBuilder(mib_symbols)


def test_build_with_textual_convention_and_scalar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Prepare fake TextualConvention base class so _is_textual_convention_symbol detects it
    class TextualConvention:
        pass

    class MyTC(TextualConvention):
        displayHint = "hint"

        class subtypeSpec:
            def __repr__(self) -> str:
                return "ValueSizeConstraint object, consts 1, 1"

    class SyntaxObj:
        def __init__(self) -> None:
            self.subtypeSpec = type(
                "S",
                (),
                {"__repr__": lambda self: "ValueSizeConstraint object, consts 2, 2"},
            )()
            # Declare namedValues so static analyzers know the attribute exists; tests may overwrite it.
            self.namedValues: Any = types.SimpleNamespace()

        def getDisplayHint(self) -> str:
            return " disp "

        def __repr__(self) -> str:
            return "SyntaxObj()"

    class ScalarObj:
        def getSyntax(self) -> object:
            # Return an object that has subtypeSpec and namedValues
            s = SyntaxObj()
            # add namedValues with items() callable
            nv = types.SimpleNamespace()
            nv.items = lambda: [("one", 1), ("two", 2)]
            s.namedValues = nv
            return s

    # Create fake mibSymbols mapping
    mib_symbols = {
        "TEST-MIB": {
            "MyTC": MyTC,
            "myScalar": ScalarObj(),
        }
    }

    fake_builder = make_fake_builder(mib_symbols)

    # Monkeypatch SnmpEngine to return object with get_mib_builder
    class FakeEngine:
        def get_mib_builder(self) -> Any:
            return fake_builder

    monkeypatch.setattr("app.type_recorder._engine.SnmpEngine", lambda: FakeEngine())

    # Monkeypatch seed to avoid heavy rfc1902 usage
    monkeypatch.setattr(
        TypeRecorder,
        "_seed_base_types",
        staticmethod(
            lambda: {
                "Integer32": {
                    "base_type": "INTEGER",
                    "constraints": [],
                    "defined_in": None,
                }
            }
        ),
    )

    # Also ensure get_snmpv2_smi_types returns at least the seeded name
    monkeypatch.setattr(TypeRecorder, "get_snmpv2_smi_types", lambda self: {"Integer32"})

    tr = TypeRecorder(tmp_path)
    tr.build()
    reg = tr.registry
    # Expect MyTC to be recorded and myScalar to be referenced in used_by
    assert "MyTC" in reg
    assert any("TEST-MIB::myScalar" in v.get("used_by", []) for v in reg.values())
