#!/usr/bin/env python3
"""Debug the enum extraction in the generator."""

from pysnmp.smi import builder
import os
import json

mib_py_path = "compiled-mibs/IF-MIB.py"
mib_name = "IF-MIB"

mibBuilder = builder.MibBuilder()
mibBuilder.add_mib_sources(builder.DirMibSource(os.path.dirname(mib_py_path)))
mibBuilder.load_modules(mib_name)
mib_symbols = mibBuilder.mibSymbols[mib_name]

if "ifAdminStatus" in mib_symbols:
    symbol_obj = mib_symbols["ifAdminStatus"]
    syntax_obj = symbol_obj.getSyntax()

    print(f"Syntax type: {type(syntax_obj).__name__}")
    print(f'Has namedValues: {hasattr(syntax_obj, "namedValues")}')
    if hasattr(syntax_obj, "namedValues"):
        named_values = dict(syntax_obj.namedValues)
        print(f"Named values: {named_values}")
        print(f"First enum value: {list(named_values.values())[0]}")

    # Now test the generator's _extract_type_info
    from app.generator import BehaviourGenerator

    gen = BehaviourGenerator("mock-behaviour", load_default_plugins=False)
    type_info = gen._extract_type_info(syntax_obj, "Integer32")
    print("\nExtracted type_info:")
    print(json.dumps(type_info, indent=2, default=str))

    # Now test with plugins
    from app.plugin_loader import load_plugins

    load_plugins()

    from plugins.basic_types import get_default_value

    default = get_default_value(type_info, "ifAdminStatus")
    print(f"\nDefault value from plugin: {default}")
