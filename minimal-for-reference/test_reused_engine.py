#!/usr/bin/env python3
"""Test what happens when reusing the same SnmpEngine across multiple calls."""
import sys
import time
from async_wrapper import get_sync, get_next_sync, make_oid
from pysnmp.hlapi.asyncio import SnmpEngine, CommunityData, ObjectType

address = ('parrot', 161)

print("=" * 70)
print("TESTING REUSED ENGINE ACROSS MULTIPLE CALLS")
print("=" * 70)

# Test 1: Create ONE engine and reuse it across multiple get_sync calls
print("\n📋 Test 1: Single engine, multiple get_sync calls")
print("-" * 70)

engine = SnmpEngine()
auth = CommunityData('public', mpModel=1)

try:
    print("Call 1: get_sync(1.3.6.1.4.1.99999.1.1.0)...")
    start = time.time()
    result1 = get_sync(engine, auth, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.1.0'))], timeout=1.0, retries=1)
    elapsed1 = time.time() - start
    print(f"  ✓ Completed in {elapsed1:.2f}s: {result1[0]}")
    
    print("Call 2: get_sync(1.3.6.1.4.1.99999.1.2.0)...")
    start = time.time()
    result2 = get_sync(engine, auth, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.2.0'))], timeout=1.0, retries=1)
    elapsed2 = time.time() - start
    print(f"  ✓ Completed in {elapsed2:.2f}s: {result2[0]}")
    
    print("Call 3: get_sync(1.3.6.1.4.1.99999.1.3.0)...")
    start = time.time()
    result3 = get_sync(engine, auth, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.3.0'))], timeout=1.0, retries=1)
    elapsed3 = time.time() - start
    print(f"  ✓ Completed in {elapsed3:.2f}s: {result3[0]}")
    
    print("✅ Test 1 PASSED: Multiple get_sync calls work with reused engine")
except Exception as e:
    print(f"❌ Test 1 FAILED: {e}")
    sys.exit(1)

# Test 2: Create ONE engine and reuse it across get_sync then get_next_sync
print("\n📋 Test 2: Single engine, interleaved get_sync + get_next_sync")
print("-" * 70)

engine2 = SnmpEngine()
auth2 = CommunityData('public', mpModel=1)

try:
    print("Call 1: get_sync(1.3.6.1.4.1.99999.1.1.0)...")
    start = time.time()
    result1 = get_sync(engine2, auth2, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.1.0'))], timeout=1.0, retries=1)
    elapsed1 = time.time() - start
    print(f"  ✓ Completed in {elapsed1:.2f}s: {result1[0]}")
    
    print("Call 2: get_next_sync(1.3.6.1.4.1.99999.1.1.0)...")
    start = time.time()
    result2 = get_next_sync(engine2, auth2, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.1.0'))], timeout=1.0, retries=1)
    elapsed2 = time.time() - start
    print(f"  ✓ Completed in {elapsed2:.2f}s: {result2[0]}")
    
    print("Call 3: get_sync(1.3.6.1.4.1.99999.1.2.0)...")
    start = time.time()
    result3 = get_sync(engine2, auth2, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.2.0'))], timeout=1.0, retries=1)
    elapsed3 = time.time() - start
    print(f"  ✓ Completed in {elapsed3:.2f}s: {result3[0]}")
    
    print("Call 4: get_next_sync(1.3.6.1.4.1.99999.1.2.0)...")
    start = time.time()
    result4 = get_next_sync(engine2, auth2, address, [ObjectType(make_oid('1.3.6.1.4.1.99999.1.2.0'))], timeout=1.0, retries=1)
    elapsed4 = time.time() - start
    print(f"  ✓ Completed in {elapsed4:.2f}s: {result4[0]}")
    
    print("✅ Test 2 PASSED: Interleaved operations work with reused engine")
except Exception as e:
    print(f"❌ Test 2 FAILED: {e}")
    sys.exit(1)

# Test 3: Simulate snmpwalk with SAME engine (the critical test)
print("\n📋 Test 3: Snmpwalk simulation with single reused engine")
print("-" * 70)

engine3 = SnmpEngine()
auth3 = CommunityData('public', mpModel=1)

try:
    current_oid = ObjectType(make_oid('1.3.6.1.4.1.99999'))
    
    print("Starting walk at 1.3.6.1.4.1.99999...")
    for i in range(5):
        print(f"\nIteration {i+1}: get_next_sync...")
        start = time.time()
        result = get_next_sync(engine3, auth3, address, [current_oid], timeout=1.0, retries=1)
        elapsed = time.time() - start
        print(f"  ✓ Completed in {elapsed:.2f}s: {result[0]}")
        
        # Check if we've walked past the enterprise root
        oid_str = str(result[0])
        if '99999' not in oid_str:
            print("  → Walked past enterprise root, stopping")
            break
        
        current_oid = result[0]
    
    print("✅ Test 3 PASSED: Snmpwalk works with reused engine")
except Exception as e:
    print(f"❌ Test 3 FAILED: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ ALL TESTS PASSED - SINGLE ENGINE CAN BE REUSED!")
print("=" * 70)
