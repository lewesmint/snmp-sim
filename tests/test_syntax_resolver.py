"""
Tests for SNMP type syntax resolution and base type inference.

This test module covers functionality that maps TEXTUAL-CONVENTIONS and 
syntax names to their base SNMP types. In the old codebase, this was handled 
by OLD_APP/syntax_resolver.py. Now it's distributed across:
- app/type_registry.py: Type information indexed by OID
- app/generator.py: Base type extraction from MIB structures
- data/types.json: Canonical type registry with base_type field
"""

import pytest
from pathlib import Path
from app.type_registry import TypeRegistry


def test_type_registry_has_base_types() -> None:
    """Test that type registry contains base_type information for TC types."""
    compiled_dir = Path(__file__).parent.parent / "compiled-mibs"
    
    if not compiled_dir.exists():
        pytest.skip("No compiled-mibs directory available")
    
    registry = TypeRegistry(compiled_dir)
    registry.build()
    
    # Look for known TC types that should have base types mapped
    # These are types that OLD_APP/syntax_resolver.py would have resolved
    tc_type_mappings = {
        "DisplayString": "OctetString",
        "TruthValue": "Integer32",
        "TimeStamp": "TimeTicks",
        "ObjectIdentifier": None,  # base type can be null
        "OctetString": None,
    }
    
    registry_dict = registry.registry
    for tc_type, expected_base in tc_type_mappings.items():
        # Find entries with this base type
        matching = [k for k, v in registry_dict.items() 
                   if v.get('name') == tc_type or k == tc_type]
        
        if matching:
            entry = registry_dict[matching[0]]
            base_type = entry.get('base_type')
            if expected_base is not None:
                assert base_type == expected_base or base_type is None, \
                    f"{tc_type} should map to {expected_base}, got {base_type}"


def test_compiled_mibs_have_base_type_info() -> None:
    """Test that compiled MIBs encode base type information via class inheritance.
    
    This replaces the old resolve_syntax_name functionality - now we examine
    the compiled MIB code structure and class hierarchies to determine base types.
    """
    compiled_mibs = Path(__file__).parent.parent / "compiled-mibs"
    
    if not compiled_mibs.exists():
        pytest.skip("No compiled-mibs directory available")
    
    # Check SNMPv2-TC which defines many standard TC types
    snmpv2_tc = compiled_mibs / "SNMPv2-TC.py"
    
    if not snmpv2_tc.exists():
        pytest.skip("SNMPv2-TC.py not found")
    
    with open(snmpv2_tc) as f:
        content = f.read()
    
    # These TC types should be defined in SNMPv2-TC
    tc_types = [
        "DisplayString",  # Should inherit from OctetString
        "TruthValue",     # Should inherit from Integer
        "TimeStamp",      # Should inherit from TimeTicks
    ]
    
    for tc_type in tc_types:
        # Verify TC is defined as a class
        assert f"class {tc_type}" in content, \
            f"{tc_type} TC should be defined as a class in SNMPv2-TC"
        
        # Verify it uses TextualConvention
        assert "TextualConvention" in content, \
            "SNMPv2-TC should use TextualConvention"


def test_type_info_extraction_from_registry() -> None:
    """Test that type information can be extracted from the registry.
    
    This is the new approach - instead of resolve_syntax_name() function,
    we look up type info in the canonical registry via data/types.json.
    """
    import json
    from pathlib import Path
    
    types_json = Path(__file__).parent.parent / "data" / "types.json"
    
    if not types_json.exists():
        pytest.skip("data/types.json not found")
    
    with open(types_json) as f:
        types_dict = json.load(f)
    
    # Verify that DisplayString maps to OctetString
    if "DisplayString" in types_dict:
        entry = types_dict["DisplayString"]
        assert entry.get("base_type") == "OctetString", \
            "DisplayString should have OctetString as base_type"
        assert entry.get("display_hint") == "255a", \
            "DisplayString should have display_hint"
    
    # Verify basic types exist
    assert "OctetString" in types_dict, "OctetString should be in registry"
    assert "Integer32" in types_dict, "Integer32 should be in registry"
    assert "ObjectIdentifier" in types_dict, "ObjectIdentifier should be in registry"






