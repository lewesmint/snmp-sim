"""Test to discover where SNMP types can be sourced from in PySNMP.

This test explores different ways to get SNMP types:
1. Direct import from pysnmp.proto.rfc1902 (base RFC types)
2. Import from MibBuilder via SNMPv2-SMI (base types)
3. Import from MibBuilder via SNMPv2-TC (textual conventions)
4. Import from pysnmp.smi.rfc1902 (alternative location)
"""

import pytest


def test_rfc1902_base_types() -> None:
    """Test which types are available directly from pysnmp.proto.rfc1902."""
    from pysnmp.proto import rfc1902

    # These should be available (base RFC 1902 types)
    base_types = [
        "OctetString",
        "Integer32",
        "Counter32",
        "Counter64",
        "Gauge32",
        "IpAddress",
        "TimeTicks",
        "ObjectIdentifier",
        "Unsigned32",
        "Integer",
        "Bits",
        "Opaque",
        "Null",
    ]

    available = {}
    for type_name in base_types:
        has_it = hasattr(rfc1902, type_name)
        available[type_name] = has_it
        if has_it:
            getattr(rfc1902, type_name)
        else:
            pass

    # All base types should be available
    assert all(available.values()), (
        f"Missing base types: {[k for k, v in available.items() if not v]}"
    )


def test_textual_conventions_not_in_rfc1902() -> None:
    """Test that TEXTUAL-CONVENTIONs are NOT in pysnmp.proto.rfc1902."""
    from pysnmp.proto import rfc1902

    # These are TEXTUAL-CONVENTIONs, should NOT be in rfc1902
    textual_conventions = [
        "DisplayString",
        "PhysAddress",
        "MacAddress",
        "TruthValue",
        "TimeStamp",
        "AutonomousType",
        "RowStatus",
        "StorageType",
    ]

    for type_name in textual_conventions:
        has_it = hasattr(rfc1902, type_name)
        assert not has_it, f"{type_name} should NOT be in rfc1902 (it's a TEXTUAL-CONVENTION)"


def test_mib_builder_snmpv2_smi() -> None:
    """Test importing base types from SNMPv2-SMI via MibBuilder."""
    from pysnmp.smi import builder

    mib_builder = builder.MibBuilder()
    mib_builder.load_modules("SNMPv2-SMI")

    # Base types from SNMPv2-SMI
    smi_types = [
        "Integer32",
        "Counter32",
        "Counter64",
        "Gauge32",
        "Unsigned32",
        "TimeTicks",
    ]

    for type_name in smi_types:
        try:
            mib_builder.import_symbols("SNMPv2-SMI", type_name)[0]
        except (
            AssertionError,
            AttributeError,
            ImportError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            pytest.fail(f"Failed to import {type_name} from SNMPv2-SMI")


def test_mib_builder_snmpv2_tc() -> None:
    """Test importing TEXTUAL-CONVENTIONs from SNMPv2-TC via MibBuilder."""
    from pysnmp.smi import builder

    mib_builder = builder.MibBuilder()
    mib_builder.load_modules("SNMPv2-TC")

    # TEXTUAL-CONVENTIONs from SNMPv2-TC
    tc_types = [
        "DisplayString",
        "PhysAddress",
        "MacAddress",
        "TruthValue",
        "TimeStamp",
        "AutonomousType",
        "RowStatus",
        "StorageType",
        "TestAndIncr",
        "TimeInterval",
        "DateAndTime",
    ]

    results = {}
    for type_name in tc_types:
        try:
            mib_builder.import_symbols("SNMPv2-TC", type_name)[0]
            results[type_name] = True
        except (
            AssertionError,
            AttributeError,
            ImportError,
            LookupError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            results[type_name] = False

    # At least the common ones should be available
    assert results.get("DisplayString"), "DisplayString should be in SNMPv2-TC"
    assert results.get("PhysAddress"), "PhysAddress should be in SNMPv2-TC"


def test_alternative_rfc1902_location() -> None:
    """Test if types are available from pysnmp.smi.rfc1902."""
    try:
        from pysnmp.smi import rfc1902

        # Try to get some types
        if hasattr(rfc1902, "OctetString"):
            pass
        if hasattr(rfc1902, "DisplayString"):
            pass

    except ImportError:
        pass


def test_create_instances() -> None:
    """Test creating actual instances of types from different sources."""
    from pysnmp.proto import rfc1902
    from pysnmp.smi import builder

    # Create from rfc1902 directly
    rfc1902.OctetString("test string")
    rfc1902.Integer32(42)

    # Create from MibBuilder
    mib_builder = builder.MibBuilder()
    mib_builder.load_modules("SNMPv2-TC")
    # pylint: disable=invalid-name
    DisplayString = mib_builder.import_symbols("SNMPv2-TC", "DisplayString")[0]

    DisplayString("display string")

    # Check if DisplayString is actually based on OctetString


def test_cannot_import_displaystring_directly() -> None:
    """Test that DisplayString CANNOT be imported directly from SNMPv2-TC file."""
    import importlib.util
    import sys

    # The file exists
    import pysnmp.smi.mibs

    mibs_path = pysnmp.smi.mibs.__path__[0]
    snmpv2_tc_path = f"{mibs_path}/SNMPv2-TC.py"

    # But we cannot import it directly because it requires mibBuilder in scope
    spec = importlib.util.spec_from_file_location("SNMPv2_TC_test", snmpv2_tc_path)

    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules["SNMPv2_TC_test"] = module

        try:
            spec.loader.exec_module(module)
            pytest.fail("SNMPv2-TC should require mibBuilder")
        except NameError as e:
            assert "mibBuilder" in str(e), "Should fail due to missing mibBuilder"
        finally:
            if "SNMPv2_TC_test" in sys.modules:
                del sys.modules["SNMPv2_TC_test"]


def test_the_only_way_to_get_displaystring() -> None:
    """Demonstrate the ONLY way to get DisplayString in user code."""
    from pysnmp.smi import builder

    # Step 1: Create MibBuilder
    mib_builder = builder.MibBuilder()

    # Step 2: Load the SNMPv2-TC module
    mib_builder.load_modules("SNMPv2-TC")

    # Step 3: Import the symbol
    # pylint: disable=invalid-name
    DisplayString = mib_builder.import_symbols("SNMPv2-TC", "DisplayString")[0]

    # Step 4: Use it
    DisplayString("Hello, SNMP!")

    assert DisplayString is not None


if __name__ == "__main__":
    test_rfc1902_base_types()
    test_textual_conventions_not_in_rfc1902()
    test_mib_builder_snmpv2_smi()
    test_mib_builder_snmpv2_tc()
    test_alternative_rfc1902_location()
    test_create_instances()
    test_cannot_import_displaystring_directly()
    test_the_only_way_to_get_displaystring()
