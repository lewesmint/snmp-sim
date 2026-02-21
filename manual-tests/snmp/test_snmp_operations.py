#!/usr/bin/env python3
"""
Test script for SNMP operations: GET, SET, GETNEXT, WALK, GETBULK
Tests against localhost:11161 using SNMPv2c
"""

import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    get_cmd,
    set_cmd,
    next_cmd,
    bulk_cmd,
    walk_cmd,
)
from pysnmp.smi.rfc1902 import ObjectType, ObjectIdentity
from pysnmp.proto.rfc1902 import OctetString


# Configuration
HOST = "127.0.0.1"
PORT = 11161
READ_COMMUNITY = "public"
WRITE_COMMUNITY = "private"


async def test_get() -> bool:
    """Test SNMP GET operation"""
    print("\n" + "=" * 60)
    print("TEST: SNMP GET")
    print("=" * 60)

    oid = "1.3.6.1.2.1.1.1.0"  # sysDescr.0

    print(f"Testing GET: {oid} from {HOST}:{PORT}")
    print(f"Community: {READ_COMMUNITY}")

    try:
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            SnmpEngine(),
            CommunityData(READ_COMMUNITY, mpModel=1),  # SNMPv2c
            await UdpTransportTarget.create((HOST, PORT)),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

        if errorIndication:
            print(f"❌ Error: {errorIndication}")
            return False
        elif errorStatus:
            print(f"❌ SNMP Error: {errorStatus} at {errorIndex}")
            return False
        else:
            print("✅ Success!")
            for varBind in varBinds:
                oid_str = varBind[0].prettyPrint()
                value = varBind[1].prettyPrint()
                print(f"  OID: {oid_str}")
                print(f"  Value: {value}")
                print(f"  Type: {type(varBind[1]).__name__}")
            return True

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_set() -> bool:
    """Test SNMP SET operation"""
    print("\n" + "=" * 60)
    print("TEST: SNMP SET")
    print("=" * 60)

    oid = "1.3.6.1.2.1.1.4.0"  # sysContact.0
    new_value = "Test Admin <test@example.com>"

    print(f"Testing SET: {oid} from {HOST}:{PORT}")
    print(f"Community: {WRITE_COMMUNITY}")
    print(f"New Value: {new_value}")

    try:
        # Perform SET
        errorIndication, errorStatus, errorIndex, varBinds = await set_cmd(
            SnmpEngine(),
            CommunityData(WRITE_COMMUNITY, mpModel=1),  # SNMPv2c
            await UdpTransportTarget.create((HOST, PORT)),
            ContextData(),
            ObjectType(ObjectIdentity(oid), OctetString(new_value)),
        )

        if errorIndication:
            print(f"❌ Error: {errorIndication}")
            return False
        elif errorStatus:
            print(f"❌ SNMP Error: {errorStatus} at {errorIndex}")
            return False
        else:
            print("✅ SET Success!")
            for varBind in varBinds:
                oid_str = varBind[0].prettyPrint()
                value = varBind[1].prettyPrint()
                print(f"  OID: {oid_str}")
                print(f"  New Value: {value}")

            # Verify with GET
            print("\nVerifying with GET...")
            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                SnmpEngine(),
                CommunityData(READ_COMMUNITY, mpModel=1),
                await UdpTransportTarget.create((HOST, PORT)),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )

            if not errorIndication and not errorStatus:
                for varBind in varBinds:
                    value = varBind[1].prettyPrint()
                    print(f"  Verified Value: {value}")
                    if value == new_value:
                        print("  ✅ Value matches!")
                        return True
                    else:
                        print(
                            f"  ⚠️  Value mismatch: expected '{new_value}', got '{value}'"
                        )
                        return False
                # If varBinds is empty
                print("  ⚠️  No varBinds returned")
                return False
            else:
                print(f"  ⚠️  Verification failed: {errorIndication or errorStatus}")
                return False

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_getnext() -> bool:
    """Test SNMP GETNEXT operation"""
    print("\n" + "=" * 60)
    print("TEST: SNMP GETNEXT")
    print("=" * 60)

    oid = "1.3.6.1.2.1.1.1"  # sysDescr (without .0)

    print(f"Testing GETNEXT: {oid} from {HOST}:{PORT}")
    print(f"Community: {READ_COMMUNITY}")

    try:
        # next_cmd returns a coroutine, await it to get ONE result
        target = await UdpTransportTarget.create((HOST, PORT))
        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
            SnmpEngine(),
            CommunityData(READ_COMMUNITY, mpModel=1),  # SNMPv2c
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

        if errorIndication:
            print(f"❌ Error: {errorIndication}")
            return False
        elif errorStatus:
            print(f"❌ SNMP Error: {errorStatus} at {errorIndex}")
            return False
        else:
            print("✅ Success!")
            for varBind in varBinds:
                oid_str = varBind[0].prettyPrint()
                value = varBind[1].prettyPrint()
                print(f"  Next OID: {oid_str}")
                print(f"  Value: {value}")
                print(f"  Type: {type(varBind[1]).__name__}")
            return True

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_walk() -> bool:
    """Test SNMP WALK operation"""
    print("\n" + "=" * 60)
    print("TEST: SNMP WALK")
    print("=" * 60)

    oid = "1.3.6.1.2.1.1"  # system group

    print(f"Testing WALK: {oid} from {HOST}:{PORT}")
    print(f"Community: {READ_COMMUNITY}")

    try:
        count = 0
        max_results = 10  # Limit for demonstration

        # walk_cmd returns async generator directly
        target = await UdpTransportTarget.create((HOST, PORT))
        iterator = walk_cmd(
            SnmpEngine(),
            CommunityData(READ_COMMUNITY, mpModel=1),  # SNMPv2c
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

        async for errorIndication, errorStatus, errorIndex, varBinds in iterator:
            if errorIndication:
                print(f"❌ Error: {errorIndication}")
                return False
            elif errorStatus:
                print(f"❌ SNMP Error: {errorStatus} at {errorIndex}")
                return False
            else:
                for varBind in varBinds:
                    count += 1
                    oid_str = varBind[0].prettyPrint()
                    value = varBind[1].prettyPrint()
                    type_name = type(varBind[1]).__name__

                    if count <= max_results:
                        print(f"  [{count}] {oid_str} = {value} ({type_name})")

                    if count == max_results:
                        print(f"  ... (limiting output to {max_results} results)")

                if count >= max_results:
                    break

        print(f"\n✅ Success! Retrieved {count} OIDs")
        return count > 0

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_bulkget() -> bool:
    """Test SNMP BULKGET operation"""
    print("\n" + "=" * 60)
    print("TEST: SNMP BULKGET")
    print("=" * 60)

    oid = "1.3.6.1.2.1.1"  # system group
    non_repeaters = 0
    max_repetitions = 5

    print(f"Testing BULKGET: {oid} from {HOST}:{PORT}")
    print(f"Community: {READ_COMMUNITY}")
    print(f"Non-repeaters: {non_repeaters}, Max-repetitions: {max_repetitions}")

    try:
        # bulk_cmd returns a coroutine, await it to get ONE bulk result
        target = await UdpTransportTarget.create((HOST, PORT))
        errorIndication, errorStatus, errorIndex, varBinds = await bulk_cmd(
            SnmpEngine(),
            CommunityData(READ_COMMUNITY, mpModel=1),  # SNMPv2c
            target,
            ContextData(),
            non_repeaters,
            max_repetitions,
            ObjectType(ObjectIdentity(oid)),
        )

        if errorIndication:
            print(f"❌ Error: {errorIndication}")
            return False
        elif errorStatus:
            print(f"❌ SNMP Error: {errorStatus} at {errorIndex}")
            return False
        else:
            print("✅ Success!")
            count = 0
            for varBind in varBinds:
                count += 1
                oid_str = varBind[0].prettyPrint()
                value = varBind[1].prettyPrint()
                type_name = type(varBind[1]).__name__
                print(f"  [{count}] {oid_str} = {value} ({type_name})")

            print(f"\nRetrieved {count} OIDs in bulk")
            return count > 0

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_snmptable() -> bool:
    """Test SNMP table walk (sysORTable)"""
    print("\n" + "=" * 60)
    print("TEST: SNMP TABLE (sysORTable)")
    print("=" * 60)

    table_oid = "1.3.6.1.2.1.1.9.1"  # sysORTable

    print(f"Testing table walk: {table_oid} from {HOST}:{PORT}")
    print(f"Community: {READ_COMMUNITY}")

    try:
        table_data: dict[str, dict[str, str]] = {}

        # walk_cmd returns async generator directly
        target = await UdpTransportTarget.create((HOST, PORT))
        iterator = walk_cmd(
            SnmpEngine(),
            CommunityData(READ_COMMUNITY, mpModel=1),  # SNMPv2c
            target,
            ContextData(),
            ObjectType(ObjectIdentity(table_oid)),
        )

        async for errorIndication, errorStatus, errorIndex, varBinds in iterator:
            if errorIndication:
                print(f"❌ Error: {errorIndication}")
                return False
            elif errorStatus:
                print(f"❌ SNMP Error: {errorStatus} at {errorIndex}")
                return False
            else:
                for varBind in varBinds:
                    oid_str = varBind[0].prettyPrint()
                    value = varBind[1].prettyPrint()

                    # Parse table entry
                    # OID format: 1.3.6.1.2.1.1.9.1.<column>.<index>
                    parts = oid_str.split(".")
                    if len(parts) >= 12:
                        column = parts[10]
                        index = ".".join(parts[11:])

                        if index not in table_data:
                            table_data[index] = {}

                        # Map column numbers to names
                        column_names = {
                            "1": "sysORIndex",
                            "2": "sysORID",
                            "3": "sysORDescr",
                            "4": "sysORUpTime",
                        }

                        col_name = column_names.get(column, f"column{column}")
                        table_data[index][col_name] = value

        if table_data:
            print("✅ Success!")
            print(f"\nTable Entries ({len(table_data)} rows):")
            print("-" * 80)

            for index, row in sorted(table_data.items()):
                print(f"\nIndex: {index}")
                for col_name, value in row.items():
                    print(f"  {col_name}: {value}")

            return True
        else:
            print("⚠️  No table data found")
            return False

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback

        traceback.print_exc()
        return False


async def run_all_tests() -> bool:
    """Run all SNMP operation tests"""
    print("\n" + "=" * 60)
    print("SNMP OPERATIONS TEST SUITE")
    print(f"Target: {HOST}:{PORT}")
    print("=" * 60)

    results = {}

    # Run each test
    results["GET"] = await test_get()
    await asyncio.sleep(0.5)  # Brief pause between tests

    results["SET"] = await test_set()
    await asyncio.sleep(0.5)

    results["GETNEXT"] = await test_getnext()
    await asyncio.sleep(0.5)

    results["WALK"] = await test_walk()
    await asyncio.sleep(0.5)

    results["BULKGET"] = await test_bulkget()
    await asyncio.sleep(0.5)

    results["SNMPTABLE"] = await test_snmptable()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, test_passed in results.items():
        status = "✅ PASS" if test_passed else "❌ FAIL"
        print(f"{test_name:15} {status}")

    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    print("-" * 60)
    print(f"Total: {passed_count}/{total} tests passed")

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
