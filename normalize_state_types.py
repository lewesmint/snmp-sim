#!/usr/bin/env python3
"""
Normalize data types in mib_state.json based on schema definitions.
Converts values to match the types defined in schema files.
"""

import json
from pathlib import Path
from typing import Any


def load_schemas(agent_model_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all schema.json files from agent-model/"""
    schemas = {}
    for mib_dir in agent_model_dir.glob("*/"):
        schema_file = mib_dir / "schema.json"
        if schema_file.exists():
            with open(schema_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Extract objects from schema
                if "objects" in data:
                    schemas.update(data["objects"])
                else:
                    schemas.update(data)
    return schemas


def get_column_type(table_oid: str, column_name: str, schemas: dict[str, Any]) -> str:
    """Get the SNMP type of a column from schema."""
    # Look up the column by name in schemas
    if column_name in schemas:
        col_data = schemas[column_name]
        if isinstance(col_data, dict):
            col_oid = col_data.get("oid", [])
            if not col_oid:
                return ""
            
            # Verify this column belongs to the table
            # Column OID format: table.1.column_index
            # So we reconstruct expected entry OID: table.1
            col_oid_str = ".".join(str(x) for x in col_oid)
            
            # Check if column OID starts with table.1
            # The entry OID is table + [1], so table.1
            expected_prefix = table_oid + ".1."
            if col_oid_str.startswith(expected_prefix):
                # This column belongs to this table
                col_type = col_data.get("type")
                if isinstance(col_type, str):
                    return col_type
                return ""
    
    return ""


def coerce_value(value: Any, column_type: str) -> Any:
    """Coerce a value to the correct type based on column_type."""
    if value is None or value == "unset":
        return None
    
    # Integer types
    if column_type in (
        "Integer32", "Counter32", "Gauge32", "Counter64", "TimeTicks",
        "Unsigned32", "Integer", "Opaque", "TestAndIncr", "InterfaceIndex",
        "InterfaceIndexOrZero", "RowStatus", "TruthValue"
    ):
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    # String types
    if column_type in (
        "DisplayString", "OwnerString", "AutonomousType", "ObjectIdentifier",
        "OCTET", "BITS"
    ):
        if isinstance(value, str):
            return value
        if isinstance(value, (list, dict)):
            return value  # Keep as-is for complex types
        return str(value)
    
    # PhysAddress - keep as string or array
    if column_type == "PhysAddress":
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return value
        return value
    
    # Default: keep as-is
    return value


def normalize_mib_state(state_file: Path, agent_model_dir: Path) -> int:
    """Normalize all values in mib_state.json based on schema types."""
    
    # Load state file
    with open(state_file, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    # Load schemas
    schemas = load_schemas(agent_model_dir)
    print(f"Loaded {len(schemas)} schema objects")
    
    # Process tables
    tables = state.get("tables", {})
    changes_made = 0
    
    for table_oid, instances in tables.items():
        if not isinstance(instances, dict):
            continue
        
        print(f"\nProcessing table: {table_oid}")
        
        for index_str, instance_data in instances.items():
            if not isinstance(instance_data, dict):
                continue
            
            column_values = instance_data.get("column_values", {})
            if not isinstance(column_values, dict):
                continue
            
            for column_name, value in list(column_values.items()):
                # Get column type from schema
                col_type = get_column_type(table_oid, column_name, schemas)
                
                if not col_type:
                    # Type not found in schema, skip
                    continue
                
                # Coerce value to correct type
                original_value = value
                coerced_value = coerce_value(value, col_type)
                
                if coerced_value != original_value and coerced_value is not None:
                    column_values[column_name] = coerced_value
                    print(f"  {column_name}[{index_str}]: {type(original_value).__name__}({original_value!r}) -> {type(coerced_value).__name__}({coerced_value!r})")
                    changes_made += 1
    
    # Write back to file
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
    
    print("\nNormalized mib_state.json")
    print(f"Changes made: {changes_made}")
    return changes_made


def main() -> None:
    workspace_root = Path(__file__).parent
    agent_model_dir = workspace_root / "agent-model"
    state_file = workspace_root / "data" / "mib_state.json"
    
    if not state_file.exists():
        print(f"ERROR: mib_state.json not found at {state_file}")
        return
    
    if not agent_model_dir.exists():
        print(f"ERROR: agent-model directory not found at {agent_model_dir}")
        return
    
    changes = normalize_mib_state(state_file, agent_model_dir)
    print(f"\nNormalization complete. {changes} value(s) converted to correct types.")


if __name__ == "__main__":
    main()
