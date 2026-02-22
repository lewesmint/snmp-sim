"""
Test to discover where SNMP types can be sourced from in PySNMP.

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
            type_class = getattr(rfc1902, type_name)
            print(f"✓ rfc1902.{type_name}: {type_class}")
        else:
            print(f"✗ rfc1902.{type_name}: NOT FOUND")

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
        print(
            f"  rfc1902.{type_name}: {'FOUND (unexpected!)' if has_it else 'not found (expected)'}"
        )
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
            type_class = mib_builder.import_symbols("SNMPv2-SMI", type_name)[0]
            print(f"✓ SNMPv2-SMI.{type_name}: {type_class}")
        except Exception as e:
            print(f"✗ SNMPv2-SMI.{type_name}: {e}")
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
            type_class = mib_builder.import_symbols("SNMPv2-TC", type_name)[0]
            results[type_name] = True
            print(f"✓ SNMPv2-TC.{type_name}: {type_class}")
        except Exception as e:
            results[type_name] = False
            print(f"✗ SNMPv2-TC.{type_name}: {e}")

    # At least the common ones should be available
    assert results.get("DisplayString"), "DisplayString should be in SNMPv2-TC"
    assert results.get("PhysAddress"), "PhysAddress should be in SNMPv2-TC"


def test_alternative_rfc1902_location() -> None:
    """Test if types are available from pysnmp.smi.rfc1902."""
    try:
        from pysnmp.smi import rfc1902

        print("\npysnmp.smi.rfc1902 exists!")
        print(f"Available: {[x for x in dir(rfc1902) if not x.startswith('_')]}")

        # Try to get some types
        if hasattr(rfc1902, "OctetString"):
            print("✓ Found OctetString in pysnmp.smi.rfc1902")
        if hasattr(rfc1902, "DisplayString"):
            print("✓ Found DisplayString in pysnmp.smi.rfc1902")

    except ImportError as e:
        print(f"pysnmp.smi.rfc1902 not available: {e}")


def test_create_instances() -> None:
    """Test creating actual instances of types from different sources."""
    from pysnmp.proto import rfc1902
    from pysnmp.smi import builder

    # Create from rfc1902 directly
    octet_str = rfc1902.OctetString("test string")
    int_val = rfc1902.Integer32(42)
    print("\nCreated from rfc1902:")
    print(f"  OctetString: {octet_str} (type: {type(octet_str)})")
    print(f"  Integer32: {int_val} (type: {type(int_val)})")

    # Create from MibBuilder
    mib_builder = builder.MibBuilder()
    mib_builder.load_modules("SNMPv2-TC")
    DisplayString = mib_builder.import_symbols("SNMPv2-TC", "DisplayString")[0]  # pylint: disable=invalid-name

    display_str = DisplayString("display string")
    print("\nCreated from MibBuilder (SNMPv2-TC):")
    print(f"  DisplayString: {display_str} (type: {type(display_str)})")

    # Check if DisplayString is actually based on OctetString
    print(f"\nDisplayString MRO: {DisplayString.__mro__}")
    print(
        f"Is DisplayString subclass of OctetString? "
        f"{issubclass(DisplayString, rfc1902.OctetString)}"
    )


def test_cannot_import_displaystring_directly() -> None:
    """Test that DisplayString CANNOT be imported directly from SNMPv2-TC file."""
    import importlib.util
    import sys

    print("\nAttempting to import SNMPv2-TC.py directly...")

    # The file exists
    import pysnmp.smi.mibs

    mibs_path = pysnmp.smi.mibs.__path__[0]
    snmpv2_tc_path = f"{mibs_path}/SNMPv2-TC.py"

    print(f"File exists at: {snmpv2_tc_path}")

    # But we cannot import it directly because it requires mibBuilder in scope
    spec = importlib.util.spec_from_file_location("SNMPv2_TC_test", snmpv2_tc_path)

    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules["SNMPv2_TC_test"] = module

        try:
            spec.loader.exec_module(module)
            print("✗ Unexpected: Module loaded without mibBuilder!")
            pytest.fail("SNMPv2-TC should require mibBuilder")
        except NameError as e:
            print(f"✓ Expected error: {e}")
            assert "mibBuilder" in str(e), "Should fail due to missing mibBuilder"
        finally:
            if "SNMPv2_TC_test" in sys.modules:
                del sys.modules["SNMPv2_TC_test"]

    print("\nConclusion: DisplayString can ONLY be obtained via MibBuilder.import_symbols()")


def test_the_only_way_to_get_displaystring() -> None:
    """Demonstrate the ONLY way to get DisplayString in user code."""
    from pysnmp.smi import builder

    print("\n" + "=" * 80)
    print("THE ONLY WAY TO GET DisplayString:")
    print("=" * 80)

    # Step 1: Create MibBuilder
    mib_builder = builder.MibBuilder()
    print("1. Create MibBuilder")

    # Step 2: Load the SNMPv2-TC module
    mib_builder.load_modules("SNMPv2-TC")
    print("2. Load SNMPv2-TC module")

    # Step 3: Import the symbol
    DisplayString = mib_builder.import_symbols("SNMPv2-TC", "DisplayString")[0]  # pylint: disable=invalid-name
    print(f"3. Import DisplayString: {DisplayString}")

    # Step 4: Use it
    ds = DisplayString("Hello, SNMP!")
    print(f"4. Create instance: {ds}")

    print("\n✓ This is the ONLY way to get DisplayString in user code!")
    print("✗ You CANNOT import it directly from pysnmp.proto.rfc1902")
    print("✗ You CANNOT import it directly from pysnmp.smi.mibs.SNMPv2_TC")

    assert DisplayString is not None


if __name__ == "__main__":
    print("=" * 80)
    print("Testing PySNMP Type Sources")
    print("=" * 80)

    test_rfc1902_base_types()
    print("\n" + "=" * 80)
    test_textual_conventions_not_in_rfc1902()
    print("\n" + "=" * 80)
    test_mib_builder_snmpv2_smi()
    print("\n" + "=" * 80)
    test_mib_builder_snmpv2_tc()
    print("\n" + "=" * 80)
    test_alternative_rfc1902_location()
    print("\n" + "=" * 80)
    test_create_instances()
    print("\n" + "=" * 80)
    test_cannot_import_displaystring_directly()
    print("\n" + "=" * 80)
    test_the_only_way_to_get_displaystring()
