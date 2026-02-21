#!/usr/bin/env python3
"""Test what StatusInformation contains"""

import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    next_cmd,
)


async def test() -> None:
    from pysnmp.proto.error import StatusInformation

    target = await UdpTransportTarget.create(("127.0.0.1", 161))

    try:
        await next_cmd(
            SnmpEngine(),
            CommunityData("public", mpModel=1),
            target,
            ContextData(),
            ObjectType(ObjectIdentity("1")),
        )
    except StatusInformation as e:
        print(f"Exception type: {type(e)}")
        print(f"Exception str: {e}")
        print(f"Exception args length: {len(e.args)}")
        if e.args:
            print(f"First arg type: {type(e.args[0])}")
            print(f"First arg value: {e.args[0]}")
            if isinstance(e.args[0], dict):
                print("It's a dict!")
                print(f"Keys: {e.args[0].keys()}")

        # Check if exception has errorIndication in args
        if e.args and isinstance(e.args[0], dict) and "errorIndication" in e.args[0]:
            print(f"\nhas errorIndication attribute: {e.args[0]['errorIndication']}")


asyncio.run(test())
