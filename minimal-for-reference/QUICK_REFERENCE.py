"""
SNMP Async Wrapper - Quick Reference Card
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from typing import Any

# ============================================================================
# 1. SETUP
# ============================================================================

from async_wrapper import (
    get_sync,
    set_sync,
    SyncSnmpClient,
    make_oid,
    shutdown_sync_wrapper,
    SnmpSyncError,
)
from pysnmp.hlapi.asyncio import SnmpEngine, ObjectType, CommunityData

# ============================================================================
# 2. AUTH OPTIONS
# ============================================================================

# SNMPv2c (Community String)
auth_v2c = CommunityData("public", mpModel=1)  # Read
auth_v2c_write = CommunityData("private", mpModel=1)  # Write

# SNMPv3 (requires pysnmp.hlapi.asyncio.UsmUserData)
from pysnmp.hlapi.asyncio import (
    UsmUserData,
    usmHMACMD5AuthProtocol,
    usmDESPrivProtocol,
)  # noqa: E402

auth_v3 = UsmUserData(
    "username",
    "authPassword",
    "privPassword",
    authProtocol=usmHMACMD5AuthProtocol,
    privProtocol=usmDESPrivProtocol,
)

# ============================================================================
# 3. BASIC OPERATIONS
# ============================================================================

# GET Single OID
engine = SnmpEngine()
auth = CommunityData("public", mpModel=1)
address = ("192.168.1.1", 161)

result = get_sync(
    engine,
    auth,
    address,
    [ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))],  # sysDescr
    timeout=1.0,
    retries=2,
)
print(result[0].prettyPrint())

# GET Multiple OIDs
result = get_sync(
    engine,
    auth,
    address,
    [
        ObjectType(make_oid("1.3.6.1.2.1.1.1.0")),  # sysDescr
        ObjectType(make_oid("1.3.6.1.2.1.1.5.0")),  # sysName
    ],
    timeout=1.0,
    retries=2,
)
for vb in result:
    print(vb.prettyPrint())

# SET Single OID
auth_write = CommunityData("private", mpModel=1)
result = set_sync(
    engine,
    auth_write,
    address,
    [ObjectType(make_oid("1.3.6.1.2.1.1.4.0"), "admin@example.com")],
    timeout=1.0,
    retries=2,
)

# ============================================================================
# 4. USING THE CLIENT CLASS
# ============================================================================

client = SyncSnmpClient(
    engine=SnmpEngine(),
    auth=CommunityData("public", mpModel=1),
    address=("192.168.1.1", 161),
    timeout=1.0,
    retries=2,
)

# GET
result = client.get(ObjectType(make_oid("1.3.6.1.2.1.1.1.0")))

# SET
result = client.set(ObjectType(make_oid("1.3.6.1.2.1.1.4.0"), "admin@example.com"))

# ============================================================================
# 5. ERROR HANDLING
# ============================================================================

try:
    result = get_sync(
        engine,
        auth,
        address,
        [ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))],
        timeout=1.0,
        retries=5,
    )
except SnmpSyncError as e:
    # Raised on:
    # - Transport errors (timeout, no route, etc)
    # - PDU errors (noAccess, notWritable, etc)
    print(f"SNMP failed: {e}")

# ============================================================================
# 6. COMMON OIDs
# ============================================================================

COMMON_OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",
    "ifNumber": "1.3.6.1.2.1.2.1.0",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",  # + interface number
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",  # + interface number
}

# Usage
result = get_sync(
    engine,
    auth,
    address,
    [ObjectType(make_oid(COMMON_OIDS["sysUpTime"]))],
    timeout=1.0,
    retries=5,
)

# ============================================================================
# 7. ADDRESS AND TRANSPORT CONFIGURATION
# ============================================================================

# Basic address tuple (timeout and retries handled by wrapper)
address = ("192.168.1.1", 161)

# Use with custom timeout/retries
result = get_sync(
    engine,
    auth,
    address=("192.168.1.1", 161),
    var_binds=[ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))],
    timeout=2.0,  # Seconds
    retries=3,  # Number of retries
)

# ============================================================================
# 8. CONTEXT (Optional)
# ============================================================================

from pysnmp.hlapi.asyncio import ContextData  # noqa: E402

context = ContextData()  # Default context
# Standard SNMP uses no context (ContextData())

result = get_sync(
    engine,
    auth,
    address,
    [ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))],
    timeout=1.0,
    retries=5,
    context=context,
)

# ============================================================================
# 9. CLEANUP
# ============================================================================

# Explicit shutdown (optional, but recommended for long-running processes)
shutdown_sync_wrapper()

# ============================================================================
# 10. FROM ASYNC CODE
# ============================================================================


async def my_async_function() -> Any:
    """This automatically works even though it's async!"""
    result = get_sync(
        engine,
        auth,
        address,
        [ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))],
        timeout=1.0,
        retries=5,
    )
    return result


# asyncio.run(my_async_function())

# ============================================================================
# REFERENCE TABLE
# ============================================================================

"""
Function Signatures:

get_sync(engine: SnmpEngine,
         auth: Union[CommunityData, UsmUserData],
         address: Tuple[str, int],
         var_binds: Sequence[ObjectType],
         timeout: float = 1.0,
         retries: int = 5,
         context: Optional[ContextData] = None) -> Tuple[ObjectType, ...]

set_sync(engine: SnmpEngine,
         auth: Union[CommunityData, UsmUserData],
         address: Tuple[str, int],
         var_binds: Sequence[ObjectType],
         timeout: float = 1.0,
         retries: int = 5,
         context: Optional[ContextData] = None) -> Tuple[ObjectType, ...]

SyncSnmpClient:
  - engine: SnmpEngine
  - auth: Union[CommunityData, UsmUserData]
  - address: Tuple[str, int]
  - timeout: float
  - retries: int
  - context: ContextData
  + get(*var_binds: ObjectType) -> Tuple[ObjectType, ...]
  + set(*var_binds: ObjectType) -> Tuple[ObjectType, ...]

make_oid(oid: str) -> ObjectIdentity

shutdown_sync_wrapper() -> None

SnmpSyncError: Exception
  - Raised on transport or SNMP errors
  - Use try/except to handle
"""

# ============================================================================
# SNMP v2c vs v3 COMPARISON
# ============================================================================

"""
SNMPv2c - Simple Community-Based
---------------------------------
Pros:
  - Simple to set up (just community string)
  - Works on older devices
  
Cons:
  - Community string in plaintext
  - No authentication or encryption

Usage:
  auth = CommunityData("public", mpModel=1)

SNMPv3 - More Secure
--------------------
Pros:
  - Authentication and encryption
  - More secure

Cons:
  - Requires user setup on agent
  - More complex configuration

Usage:
  from pysnmp.hlapi import UsmUserData, usmHMACMD5AuthProtocol, usmDESPrivProtocol
  auth = UsmUserData(username, authPass, privPass, 
                    authProtocol=..., privProtocol=...)

Recommendation:
  - Use SNMPv2c for testing/internal use
  - Use SNMPv3 for production/untrusted networks
"""
