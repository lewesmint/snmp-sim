#!/usr/bin/env python3
import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, next_cmd
)

async def test() -> None:
    target = await UdpTransportTarget.create(("127.0.0.1", 161))
    
    result = await next_cmd(
        SnmpEngine(),
        CommunityData("public", mpModel=1),
        target,
        ContextData(),
        ObjectType(ObjectIdentity("1"))
    )
    
    print(f"Result type: {type(result)}")
    print(f"Result: {result}")
    
    if isinstance(result, tuple) and len(result) >= 1:
        print(f"First element: {result[0]}")
        print(f"First element type: {type(result[0])}")

asyncio.run(test())
