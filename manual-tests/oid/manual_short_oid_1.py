#!/usr/bin/env python3
"""Test all SNMP operations with short OID "1" to verify retry logic"""

import asyncio
from typing import Any
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    next_cmd,
    walk_cmd,
)


class FakeLogger:
    def log(self, msg: str, level: str = "INFO") -> None:
        if level == "ERROR":
            print(f"  [{level}] {msg}")


async def test_get_with_oid_1() -> bool:
    """Test GET with OID 1"""
    logger = FakeLogger()
    oid = "1"
    host, port, community = "127.0.0.1", 161, "public"

    async def async_get() -> tuple[Any, ...]:
        from pysnmp.proto.error import StatusInformation

        try:
            return await get_cmd(  # type: ignore[no-any-return]
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                await UdpTransportTarget.create((host, port)),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
        except StatusInformation as e:
            error_ind = e.get("errorIndication")
            if str(error_ind) == "SNMP message serialization error" and oid == "1":
                try:
                    logger.log("Retrying GET with normalized OID: 1.0")
                    return await get_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        await UdpTransportTarget.create((host, port)),
                        ContextData(),
                        ObjectType(ObjectIdentity("1.0")),
                    )
                except StatusInformation as retry_e:
                    error_indication = retry_e.get("errorIndication", str(retry_e))
                    return (error_indication, None, None, [])
            else:
                error_indication = error_ind or str(e)
                return (error_indication, None, None, [])

    errorIndication, errorStatus, errorIndex, varBinds = await async_get()

    if not errorIndication and not errorStatus and varBinds:
        print(f"✅ GET with OID '1': {len(varBinds)} result(s)")
        return True
    else:
        print(f"❌ GET with OID '1': error={errorIndication}")
        return False


async def test_getnext_with_oid_1() -> bool:
    """Test GETNEXT with OID 1"""
    logger = FakeLogger()
    oid = "1"
    host, port, community = "127.0.0.1", 161, "public"

    async def async_next() -> tuple[Any, ...]:
        from pysnmp.proto.error import StatusInformation

        target = await UdpTransportTarget.create((host, port))

        try:
            return await next_cmd(  # type: ignore[no-any-return]
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
        except StatusInformation as e:
            error_ind = e.get("errorIndication")
            if str(error_ind) == "SNMP message serialization error" and oid == "1":
                try:
                    logger.log("Retrying GETNEXT with normalized OID: 1.0")
                    return await next_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(ObjectIdentity("1.0")),
                    )
                except StatusInformation as retry_e:
                    error_indication = retry_e.get("errorIndication", str(retry_e))
                    return (error_indication, None, None, [])
            else:
                error_indication = error_ind or str(e)
                return (error_indication, None, None, [])

    errorIndication, errorStatus, errorIndex, varBinds = await async_next()

    if not errorIndication and not errorStatus and varBinds:
        print(f"✅ GETNEXT with OID '1': {len(varBinds)} result(s)")
        return True
    else:
        print(f"❌ GETNEXT with OID '1': error={errorIndication}")
        return False


async def test_walk_with_oid_1() -> bool:
    """Test WALK with OID 1"""
    logger = FakeLogger()
    oid = "1"
    host, port, community = "127.0.0.1", 161, "public"

    async def async_walk() -> list[tuple[Any, ...]]:
        from pysnmp.proto.error import StatusInformation

        walk_results = []
        target = await UdpTransportTarget.create((host, port))

        try:
            iterator = walk_cmd(
                SnmpEngine(),
                CommunityData(community, mpModel=1),
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            count = 0
            async for errorIndication, errorStatus, errorIndex, varBinds in iterator:
                walk_results.append(
                    (errorIndication, errorStatus, errorIndex, varBinds)
                )
                count += 1
                if count >= 5:  # Limit to 5 results for test
                    break
        except StatusInformation as e:
            error_ind = e.get("errorIndication")
            if str(error_ind) == "SNMP message serialization error" and oid == "1":
                try:
                    logger.log("Retrying WALK with normalized OID: 1.0")
                    iterator = walk_cmd(
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(ObjectIdentity("1.0")),
                    )
                    count = 0
                    async for (
                        errorIndication,
                        errorStatus,
                        errorIndex,
                        varBinds,
                    ) in iterator:
                        walk_results.append(
                            (errorIndication, errorStatus, errorIndex, varBinds)
                        )
                        count += 1
                        if count >= 5:  # Limit to 5 results for test
                            break
                except StatusInformation as retry_e:
                    retry_error = retry_e.get("errorIndication", str(retry_e))
                    walk_results.append((retry_error, None, None, []))
            else:
                error_indication = error_ind or str(e)
                walk_results.append((error_indication, None, None, []))

        return walk_results

    walk_results = await async_walk()

    # Count successful results (no errorIndication)
    successful = sum(1 for err, _, _, _ in walk_results if not err)
    if successful > 0:
        print(f"✅ WALK with OID '1': {successful} result(s) returned")
        return True
    else:
        print("❌ WALK with OID '1': no results")
        return False


async def main() -> bool:
    print("\n" + "=" * 60)
    print("Testing SNMP Operations with Short OID '1'")
    print("=" * 60 + "\n")

    results = []
    results.append(await test_get_with_oid_1())
    results.append(await test_getnext_with_oid_1())
    results.append(await test_walk_with_oid_1())

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} operations successful with OID '1'")
    print("=" * 60 + "\n")

    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
