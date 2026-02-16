#!/usr/bin/env python3
"""Quick verification that all sync functions work."""
from async_wrapper import get_sync, get_next_sync, make_oid, SyncSnmpClient
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType

engine = SnmpEngine()
auth = CommunityData('public', mpModel=1)
address = ('parrot', 161)

print('Testing synchronous SNMP wrapper functions:')
print('=' * 60)

# Test 1: get_sync
print('\n1. get_sync(1.3.6.1.4.1.99999.1.1.0)')
result = get_sync(engine, auth, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.1.0'))], timeout=1.0, retries=1)
for var_bind in result:
    print(f'   ✓ {var_bind}')

# Test 2: get_next_sync
print('\n2. get_next_sync(1.3.6.1.4.1.99999.1.1.0)')
result = get_next_sync(engine, auth, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.1.0'))], timeout=1.0, retries=1)
for var_bind in result:
    print(f'   ✓ {var_bind}')

# Test 3: SyncSnmpClient
print('\n3. SyncSnmpClient')
client = SyncSnmpClient(engine=engine, auth=auth, address=address, timeout=1.0, retries=1)
result = client.get(ObjectType(make_oid('1.3.6.1.4.1.99999.1.1.0')))
print(f'   ✓ client.get() works')
result = client.get_next(ObjectType(make_oid('1.3.6.1.4.1.99999.1.1.0')))
print(f'   ✓ client.get_next() works')

print('\n' + '=' * 60)
print('✅ All synchronous functions work!')
print('=' * 60)
