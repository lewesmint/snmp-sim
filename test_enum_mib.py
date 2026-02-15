#!/usr/bin/env python3
"""Quick test of TEST-ENUM-MIB dependency resolution after directory search fix."""

from app.mib_dependency_resolver import MibDependencyResolver
import os

# Test with TEST-ENUM-MIB (now in data/mibs/fake/ subdirectory)
agent_model_folder = os.path.join(os.getcwd(), 'agent-model')
resolver = MibDependencyResolver(agent_model_folder)

# Test TEST-ENUM-MIB which is in data/mibs/fake/
mib_names = ['TEST-ENUM-MIB']
tree = resolver.build_dependency_tree(mib_names)

print('TEST: Checking TEST-ENUM-MIB dependencies after recursive fix')
print('Configured MIBs:', mib_names)
print('Total MIBs in tree:', len(tree))
print()
if 'TEST-ENUM-MIB' in tree:
    info = tree['TEST-ENUM-MIB']
    print('TEST-ENUM-MIB:')
    print(f'  Direct deps: {info.get("direct_deps", [])}')
    print(f'  Transitive deps: {info.get("transitive_deps", [])}')
    print(f'  Is configured: {info.get("is_configured", False)}')
else:
    print('TEST-ENUM-MIB not found in tree')
print()
print('All MIBs in tree:', list(tree.keys()))
