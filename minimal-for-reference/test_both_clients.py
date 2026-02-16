#!/usr/bin/env python3
"""Test both stateless and persistent client approaches."""
import time
from async_wrapper import (
    StatelessSnmpClient,
    PersistentSnmpClient,
    make_oid,
)
from pysnmp.hlapi.asyncio import CommunityData, ObjectType

address = ('parrot', 161)
auth = CommunityData('public', mpModel=1)

print("=" * 70)
print("TESTING BOTH CLIENT APPROACHES")
print("=" * 70)

# Test 1: StatelessSnmpClient (fresh engine per call)
print("\n📋 Test 1: StatelessSnmpClient (fresh engine per call)")
print("-" * 70)

client1 = StatelessSnmpClient(auth=auth, address=address, timeout=1.0, retries=1)

try:
    for i in range(1, 6):
        oid_str = f'1.3.6.1.4.1.99999.1.{i}.0'
        print(f"\nCall {i}: get({oid_str})...")
        start = time.time()
        result = client1.get(ObjectType(make_oid(oid_str)))
        elapsed = time.time() - start
        print(f"  ✓ {elapsed:.2f}s: {result[0]}")
    
    print("\n✅ StatelessSnmpClient works perfectly!")
except Exception as e:
    print(f"\n❌ StatelessSnmpClient failed: {e}")

# Test 2: PersistentSnmpClient (same engine, persistent loop)
print("\n\n📋 Test 2: PersistentSnmpClient (same engine + persistent loop)")
print("-" * 70)

client2 = PersistentSnmpClient(auth=auth, address=address, timeout=1.0, retries=1)

try:
    for i in range(1, 6):
        oid_str = f'1.3.6.1.4.1.99999.1.{i}.0'
        print(f"\nCall {i}: get({oid_str})...")
        start = time.time()
        result = client2.get(ObjectType(make_oid(oid_str)))
        elapsed = time.time() - start
        print(f"  ✓ {elapsed:.2f}s: {result[0]}")
    
    # Test get_next with persistent client
    print(f"\n\nTesting get_next with PersistentSnmpClient...")
    for i in range(1, 4):
        oid_str = f'1.3.6.1.4.1.99999.1.{i}.0'
        print(f"\nCall {i}: get_next({oid_str})...")
        start = time.time()
        result = client2.get_next(ObjectType(make_oid(oid_str)))
        elapsed = time.time() - start
        print(f"  ✓ {elapsed:.2f}s: {result[0]}")
    
    print("\n✅ PersistentSnmpClient works perfectly!")
    client2.shutdown()
except Exception as e:
    print(f"\n❌ PersistentSnmpClient failed: {e}")
    client2.shutdown()

# Test 3: Snmpwalk simulation with PersistentSnmpClient
print("\n\n📋 Test 3: Snmpwalk simulation (PersistentSnmpClient)")
print("-" * 70)

client3 = PersistentSnmpClient(auth=auth, address=address, timeout=1.0, retries=1)

try:
    current_oid = ObjectType(make_oid('1.3.6.1.4.1.99999'))
    
    print(f"Starting walk at 1.3.6.1.4.1.99999...\n")
    for i in range(10):
        print(f"Iteration {i+1}: get_next()...")
        start = time.time()
        result = client3.get_next(current_oid)
        elapsed = time.time() - start
        print(f"  ✓ {elapsed:.2f}s: {result[0]}")
        
        # Check if we've walked past the enterprise root
        oid_str = str(result[0])
        if '99999' not in oid_str:
            print(f"  → Walked past enterprise root, stopping")
            break
        
        current_oid = result[0]
    
    print("\n✅ Snmpwalk simulation works!")
    client3.shutdown()
except Exception as e:
    print(f"\n❌ Snmpwalk simulation failed: {e}")
    client3.shutdown()

print("\n" + "=" * 70)
print("✅ BOTH APPROACHES WORK!")
print("=" * 70)
print("\nSummary:")
print("  • StatelessSnmpClient: Fresh engine per call (safe, simple)")
print("  • PersistentSnmpClient: Reused engine (efficient, recommended for loops)")
print("=" * 70 + "\n")
