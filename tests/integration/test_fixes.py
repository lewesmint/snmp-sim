#!/usr/bin/env python3
"""Test script to verify the default value fixes."""

import sys
sys.path.insert(0, 'compiled-mibs')

from pysnmp.smi import builder
from app.generator import BehaviourGenerator
import json


def test_default_value_fixes() -> None:
    """Test the default value fixes."""
    # Create a generator
    gen = BehaviourGenerator('agent-model', load_default_plugins=False)

    # Load the compiled MIB manually
    mibBuilder = builder.MibBuilder()
    mibBuilder.add_mib_sources(builder.DirMibSource('compiled-mibs'))
    mibBuilder.load_modules('IF-MIB')

    # Get mib view
    from pysnmp.smi import view
    mibView = view.MibViewController(mibBuilder)

    # Find ifAdminStatus by OID (1.3.6.1.2.1.2.2.1.7)
    try:
        modName, symName, indices = mibView.getNodeName((1, 3, 6, 1, 2, 1, 2, 2, 1, 7))
        print(f'Symbol: {symName}')
        
        # Get the symbol from mibBuilder
        mibNode = mibView.getNode(modName, symName)
        syntax = mibNode.getSyntax()
    
        print(f'Type: {type(syntax).__name__}')
        print(f'Has namedValues: {hasattr(syntax, "namedValues")}')
        if hasattr(syntax, 'namedValues'):
            print(f'Named values: {dict(syntax.namedValues)}')
        
        # Now try extracting with the generator method
        type_info = gen._extract_type_info(syntax, type(syntax).__name__)
        print('\nExtracted type info:')
        print(json.dumps(type_info, indent=2, default=str))
        
        # Now test what the plugin would return
        from plugins.basic_types import get_default_value
        default = get_default_value(type_info, 'ifAdminStatus')
        print(f'\nPlugin default value: {default}')
    except Exception as e:
        print(f'Error: {e}')
    import traceback
    traceback.print_exc()
