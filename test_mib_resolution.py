#!/usr/bin/env python3
"""Test if we can resolve MIB names to OIDs using pysnmp's SMI"""
import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    ObjectIdentity
)
from pysnmp.smi import builder, view

async def test_mib_name_resolution() -> None:
    """Test resolving MIB names to OIDs"""
    print("\nTesting MIB name resolution:\n")
    
    # Create MIB builder and view
    mibBuilder = builder.MibBuilder()
    mibView = view.MibViewController(mibBuilder)
    
    # Load standard MIBs
    print("Loading SNMPv2-MIB...")
    mibBuilder.loadModules('SNMPv2-MIB')
    
    test_cases = [
        ("sysDescr", "SNMPv2-MIB-style lookup"),
        ("SNMPv2-MIB", "sysDescr", "Full SMI lookup"),
    ]
    
    print("\nResolving MIB names:\n")
    
    # Test simple name resolution
    try:
        # Try to resolve sysDescr
        oid_obj = ObjectIdentity('sysDescr')
        print(f"sysDescr resolves to: {oid_obj}")
    except Exception as e:
        print(f"Failed to resolve sysDescr: {e}")
    
    try:
        # Try to resolve with module
        oid_obj = ObjectIdentity('SNMPv2-MIB', 'sysDescr')
        print(f"SNMPv2-MIB::sysDescr resolves to: {oid_obj}")
    except Exception as e:
        print(f"Failed to resolve SNMPv2-MIB::sysDescr: {e}")
    
    # Test reverse resolution (OID to name)
    print("\nTesting reverse resolution (OID to name):\n")
    
    try:
        # Try to resolve OID to name
        oid_obj = ObjectIdentity('1.3.6.1.2.1.1.1.0')
        modName, symName, indices = mibView.get_node_name_by_oid(oid_obj)
        print(f"OID 1.3.6.1.2.1.1.1.0 resolves to: {modName}::{symName}.{'.'.join([str(i) for i in indices])}")
        print(f"Name: {symName}")
        print(f"Indices: {indices}")
        
        # Try to resolve back
        try:
            oid_obj = ObjectIdentity(modName, symName, *indices)
            print(f"Resolved back to OID: {oid_obj}")
        except Exception as e:
            print(f"Failed to resolve back: {e}")
    
    except Exception as e:
        print(f"Failed to resolve OID: {e}")

if __name__ == "__main__":
    asyncio.run(test_mib_name_resolution())
