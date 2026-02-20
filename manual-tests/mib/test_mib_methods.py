#!/usr/bin/env python3
"""Test MIB name resolution - find the right method"""
from pysnmp.smi import builder, view

# Create MIB builder and view
mibBuilder = builder.MibBuilder()
mibView = view.MibViewController(mibBuilder)

# Load standard MIBs
print("Loading SNMPv2-MIB...")
mibBuilder.load_modules('SNMPv2-MIB')

# List available methods on MibViewController
print("\nAvailable methods on MibViewController:")
methods = [m for m in dir(mibView) if not m.startswith('_')]
for method in sorted(methods):
    print(f"  - {method}")

# Try to find a lookup method
print("\n\nTrying different lookup approaches:")

# Approach 1: Check if there's a direct name lookup
try:
    result = mibView.lookup('SNMPv2-MIB', 'sysDescr')
    print(f"✅ lookup() works: {result}")
except Exception as e:
    print(f"❌ lookup() failed: {e}")

# Approach 2: Try getNodeName with just string
try:
    result = mibView.get_node_name('sysDescr')
    print(f"✅ get_node_name('sysDescr') works: {result}")
except Exception as e:
    print(f"❌ get_node_name('sysDescr') failed: {e}")

# Approach 3: Check mibBuilder methods
print("\n\nAvailable methods on MibBuilder:")
builder_methods = [m for m in dir(mibBuilder) if not m.startswith('_') and 'import' in m.lower() or 'load' in m.lower() or 'lookup' in m.lower()]
for method in sorted(builder_methods):
    print(f"  - {method}")

# Approach 4: Try the SMI module
print("\n\nChecking pysnmp.smi modules:")

try:
    from pysnmp import smi
    print("✅ smi module available")
    # Check if there's a compiler/loader
    print(f"  - smi attributes: {[a for a in dir(smi) if not a.startswith('_')]}")
except Exception:
    pass
