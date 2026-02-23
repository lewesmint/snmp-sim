# SNMP Wrapper - Quick Reference

## Imports

```python
from snmp_wrapper import (
    StatelessSnmpClient,
    PersistentSnmpClient,
    get_sync, set_sync, get_next_sync,
    make_oid,
    SnmpSyncError,
    shutdown_sync_wrapper,
)
from pysnmp.hlapi.asyncio import CommunityData, ObjectType, ObjectIdentity
```

## Pattern 1: Stateless (Simple)

```python
from snmp_wrapper import StatelessSnmpClient, make_oid
from pysnmp.hlapi.asyncio import CommunityData, ObjectType

client = StatelessSnmpClient(
    auth=CommunityData("public", mpModel=1),
    address=("192.168.1.1", 161),
    timeout=1.0,
    retries=1,
)

# GET
result = client.get(ObjectType(make_oid("1.3.6.1.2.1.1.1.0")))
print(result[0])

# SET
from pysnmp.hlapi.asyncio import OctetString
result = client.set(
    ObjectType(ObjectIdentity("1.3.6.1.2.1.1.4.0"), OctetString("admin@example.com"))
)

# GET-NEXT (single operation)
result = client.get_next(ObjectType(make_oid("1.3.6.1.2.1.1.1.0")))
```

## Pattern 2: Persistent (Fast Loop)

```python
from snmp_wrapper import PersistentSnmpClient, make_oid
from pysnmp.hlapi.asyncio import CommunityData, ObjectType

client = PersistentSnmpClient(
    auth=CommunityData("public", mpModel=1),
    address=("192.168.1.1", 161),
    timeout=1.0,
    retries=1,
)

# Snmpwalk simulation
current_oid = ObjectType(make_oid("1.3.6.1.4.1.1"))

for i in range(100):
    try:
        result = client.get_next(current_oid)
        oid_str = str(result[0])
        print(oid_str)
        
        # Stop at boundary
        if not oid_str.startswith("1.3.6.1.4.1"):
            break
            
        current_oid = result[0]
    except Exception as e:
        print(f"Error: {e}")
        break

# Cleanup
client.shutdown()
```

## Pattern 3: Direct Sync Functions

```python
from snmp_wrapper import get_sync, set_sync, get_next_sync, make_oid
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType

engine = SnmpEngine()
auth = CommunityData("public", mpModel=1)
address = ("192.168.1.1", 161)

# Basic: fresh loop per call (default)
result = get_sync(engine, auth, address, [ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))])

# Or: persistent loop (for engine reuse)
result = get_sync(
    engine, auth, address, 
    [ObjectType(make_oid("1.3.6.1.2.1.1.1.0"))],
    use_persistent_loop=True,
)
```

## Error Handling

```python
from snmp_wrapper import SnmpSyncError, StatelessSnmpClient, make_oid
from pysnmp.hlapi.asyncio import CommunityData, ObjectType

client = StatelessSnmpClient(
    auth=CommunityData("public", mpModel=1),
    address=("192.168.1.1", 161),
)

try:
    result = client.get(ObjectType(make_oid("1.3.6.1.2.1.1.1.0")))
    print(result[0])
except SnmpSyncError as e:
    print(f"SNMP error: {e}")
```

## Common OIDs

```python
make_oid("1.3.6.1.2.1.1.1.0")      # sysDescr
make_oid("1.3.6.1.2.1.1.3.0")      # sysUpTime
make_oid("1.3.6.1.2.1.1.4.0")      # sysContact
make_oid("1.3.6.1.2.1.1.5.0")      # sysName
make_oid("1.3.6.1.2.1.25.3.2.1.5.1")  # RAM available
```

## Tips

✓ **Stateless client**: Use for scripts, one-off queries, multiple agents  
✓ **Persistent client**: Use for snmpwalk, loops, polling, single agent  
✓ **Remember**: Call `client.shutdown()` on PersistentSnmpClient when done  
✓ **Timeout**: Set reasonable timeouts to avoid hanging on unreachable agents  
✓ **Retries**: Usually 1-5 retries is enough  

## Performance

| Operation | Time |
|-----------|------|
| StatelessSnmpClient.get() | ~0.20s |
| PersistentSnmpClient.get() (1st) | ~0.19s |
| PersistentSnmpClient.get() (2nd+) | ~0.16s |
| 10-OID snmpwalk | ~2.0s (persistent) |

---

**Copy this file alongside `snmp_wrapper.py` in your project.**
