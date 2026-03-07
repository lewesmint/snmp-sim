#!/usr/bin/env python3
"""Test script to verify the default value fixes."""

import sys

import pytest

sys.path.insert(0, "compiled-mibs")


from pysnmp.smi import builder

from app.generator import BehaviourGenerator


def test_default_value_fixes() -> None:
    """Test the default value fixes."""
    # Create a generator
    gen = BehaviourGenerator("agent-model", load_default_plugins=False)

    # Load the compiled MIB manually
    mibBuilder = builder.MibBuilder()
    mibBuilder.add_mib_sources(builder.DirMibSource("compiled-mibs"))
    try:
        mibBuilder.load_modules("IF-MIB")
    except (AttributeError, ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError):
        pytest.skip("IF-MIB is not available in the local compiled-mibs source")

    # Get ifAdminStatus directly from IF-MIB
    mibNode = mibBuilder.import_symbols("IF-MIB", "ifAdminStatus")[0]
    syntax_getter = getattr(mibNode, "getSyntax", None)
    syntax = syntax_getter() if callable(syntax_getter) else getattr(mibNode, "syntax", None)
    assert syntax is not None

    # Now try extracting with the generator method
    type_info = gen._extract_type_info(syntax, type(syntax).__name__)
    assert isinstance(type_info, dict)
    assert type_info

    # Now test what the plugin would return
    from plugins.basic_types import get_default_value

    default_value = get_default_value(type_info, "ifAdminStatus")
    assert default_value is not None
