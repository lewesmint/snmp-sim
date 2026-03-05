#!/usr/bin/env python3
"""Schema-driven SNMP agent (tables + scalars, multi-module export)."""

from __future__ import annotations

import json
from typing import Any, Tuple, Type, cast

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.proto.rfc1902 import Integer32, ObjectIdentifier, OctetString, TimeTicks

TYPE_MAP: dict[str, Type[Any]] = {
    "integer32": Integer32,
    "integer": Integer32,
    "octetstring": OctetString,
    "string": OctetString,
    "objectidentifier": ObjectIdentifier,
    "oid": ObjectIdentifier,
    "timeticks": TimeTicks,
}


def load_data(json_file: str = "data.json") -> dict[str, Any]:
    """Load SNMP data from JSON file."""
    from pathlib import Path

    script_dir = Path(__file__).resolve().parent
    json_path = script_dir / json_file
    with json_path.open("r", encoding="utf-8") as handle:
        return cast(dict[str, Any], json.load(handle))


def oid_str_to_tuple(oid_str: str) -> tuple[int, ...]:
    """Convert OID string to tuple of ints."""
    oid_str = oid_str.strip()
    if oid_str.startswith("."):
        oid_str = oid_str[1:]
    if not oid_str:
        return tuple()
    return tuple(int(x) for x in oid_str.split("."))


def type_from_name(type_name: str) -> Type[Any]:
    """Get SNMP type class from a string name."""
    key = type_name.strip().lower()
    if key not in TYPE_MAP:
        raise ValueError(f"Unsupported type: {type_name}")
    return TYPE_MAP[key]


def convert_value(value: Any, type_name: str) -> Any:
    """Convert a JSON value to a PySNMP value."""
    snmp_type = type_from_name(type_name)

    if snmp_type is Integer32:
        return Integer32(int(value))

    if snmp_type is TimeTicks:
        return TimeTicks(int(value))

    if snmp_type is ObjectIdentifier:
        if isinstance(value, (tuple, list)):
            return ObjectIdentifier(tuple(int(x) for x in value))
        if isinstance(value, str):
            return ObjectIdentifier(oid_str_to_tuple(value))
        raise TypeError(
            "ObjectIdentifier value must be an OID string or a list/tuple of ints"
        )

    return OctetString(str(value))


def normalize_index_tuple(index_value: Any) -> Tuple[Any, ...]:
    """Normalise index field to a tuple."""
    if isinstance(index_value, list):
        return tuple(index_value)
    return (index_value,)


def iter_modules(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Support both:
      - {"modules": [...]}  (new)
      - {"mib": {...}}      (old single-module)
    """
    if "modules" in data:
        modules = data["modules"]
        if not isinstance(modules, list):
            raise TypeError('"modules" must be a list')
        return modules

    if "mib" in data:
        mib = data["mib"]
        if not isinstance(mib, dict):
            raise TypeError('"mib" must be an object')
        return [mib]

    raise KeyError('Expected top-level key "modules" or "mib"')


def add_vacm_for_roots(
    snmp_engine: engine.SnmpEngine, roots: list[tuple[int, ...]]
) -> None:
    """
    Allow reads under each root OID.
    PySNMP VACM entries are additive, so we can call add_vacm_user once per subtree.
    """
    for root in roots:
        config.add_vacm_user(
            snmp_engine,
            2,  # SNMPv2c
            "public-read",
            "noAuthNoPriv",
            root,
            root,
        )


def main() -> None:
    data = load_data()
    modules = iter_modules(data)

    snmp_engine = engine.SnmpEngine()

    dispatcher = AsyncioDispatcher()
    snmp_engine.register_transport_dispatcher(dispatcher)

    config.add_transport(
        snmp_engine,
        config.SNMP_UDP_DOMAIN,
        udp.UdpAsyncioTransport().open_server_mode(("127.0.0.1", 1661)),
    )

    config.add_v1_system(snmp_engine, "public-read", "public")

    roots = [oid_str_to_tuple(m["rootOid"]) for m in modules if "rootOid" in m]
    add_vacm_for_roots(snmp_engine, roots)

    snmp_context = context.SnmpContext(snmp_engine)

    mib_instrum = snmp_context.get_mib_instrum()
    mib_builder = mib_instrum.get_mib_builder()

    symbols = mib_builder.import_symbols(
        "SNMPv2-SMI",
        "MibTable",
        "MibTableRow",
        "MibTableColumn",
        "MibScalarInstance",
    )
    MibTable, MibTableRow, MibTableColumn, MibScalarInstance = symbols

    for module in modules:
        module_name = module["name"]
        export_symbols: dict[str, Any] = {}

        # Scalars
        for scalar in module.get("scalars", []):
            scalar_oid = oid_str_to_tuple(scalar["oid"])
            scalar_type = scalar["type"]
            scalar_value = convert_value(scalar["value"], scalar_type)

            # Scalars are always instance ".0"
            if not scalar_oid or scalar_oid[-1] != 0:
                raise ValueError(f"Scalar OID must end with .0: {scalar['oid']}")

            base_oid = scalar_oid[:-1]
            inst = MibScalarInstance(base_oid, (0,), scalar_value)

            name = scalar.get("name", "scalar")
            export_symbols[f"{name}Inst"] = inst

        # Tables
        for table in module.get("tables", []):
            table_oid = oid_str_to_tuple(table["oid"])
            entry_oid = oid_str_to_tuple(table["entry"]["oid"])

            table_obj = MibTable(table_oid)

            index_names = [idx["name"] for idx in table["entry"]["indexes"]]
            index_specs = tuple((0, module_name, name) for name in index_names)
            entry_obj = MibTableRow(entry_oid).setIndexNames(*index_specs)

            export_symbols[table["name"]] = table_obj
            export_symbols[table["entry"]["name"]] = entry_obj

            columns_by_name: dict[str, dict[str, Any]] = {}
            for col in table["columns"]:
                col_oid = oid_str_to_tuple(col["oid"])
                col_type = type_from_name(col["type"])()
                col_access = col.get("access", "read-only")
                col_obj = MibTableColumn(col_oid, col_type).setMaxAccess(col_access)
                export_symbols[col["name"]] = col_obj
                columns_by_name[col["name"]] = col

            for row in table["rows"]:
                index_tuple = normalize_index_tuple(row["index"])
                values = row.get("values", {})

                for col_name, col in columns_by_name.items():
                    if col_name in values:
                        value = values[col_name]
                    elif col_name in index_names:
                        idx_pos = index_names.index(col_name)
                        value = index_tuple[idx_pos]
                    else:
                        continue

                    inst = MibScalarInstance(
                        oid_str_to_tuple(col["oid"]),
                        index_tuple,
                        convert_value(value, col["type"]),
                    )
                    inst_name = f"{col_name}Inst_{'_'.join(map(str, index_tuple))}"
                    export_symbols[inst_name] = inst

        mib_builder.export_symbols(module_name, **export_symbols)

    cmdrsp.GetCommandResponder(snmp_engine, snmp_context)
    cmdrsp.NextCommandResponder(snmp_engine, snmp_context)
    cmdrsp.BulkCommandResponder(snmp_engine, snmp_context)

    print("SNMP Agent Started")
    print("==================")
    print("Listening on: 127.0.0.1:1661")
    print("Community: public")
    print()

    for module in modules:
        print(f"Module: {module['name']}")
        print(f"  Root OID: {module['rootOid']}")
        if module.get("scalars"):
            print(f"  Scalars: {len(module['scalars'])}")
        if module.get("tables"):
            for table in module["tables"]:
                rows = len(table["rows"])
                print(f"  Table: {table['name']} at {table['oid']} ({rows} rows)")
        print()

    print("Test commands:")
    print("  snmpget -v2c -c public 127.0.0.1:1661 sysDescr.0")
    print("  snmpget -v2c -c public 127.0.0.1:1661 sysName.0")
    print("  snmpwalk -v2c -c public 127.0.0.1:1661 .1.3.6.1.2.1.1")
    print("  snmpwalk -v2c -c public 127.0.0.1:1661 .1.3.6.1.4.1.99999.1")
    print(
        "  snmptable -v2c -c public -m +EXAMPLE-MIB -M +. 127.0.0.1:1661 exampleTable"
    )
    print("\nPress Ctrl+C to stop.\n")

    try:
        snmp_engine.transport_dispatcher.run_dispatcher()
    except KeyboardInterrupt:
        print("\nAgent stopped.")


if __name__ == "__main__":
    main()
