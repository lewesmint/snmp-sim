# Type Aliases Module

## Overview

The `app/types.py` module provides centralized type aliases used throughout the SNMP agent codebase. This ensures consistency and improves type safety across the application.

## Available Type Aliases

### `TypeInfo`
```python
TypeInfo = Dict[str, Any]
```
Represents a **SINGLE** type entry in the registry. Contains metadata about one SNMP type including:
- `base_type`: The base ASN.1 type
- `display_hint`: Formatting hints
- `size`: Size constraints
- `constraints`: Value constraints
- `enums`: Enumeration values
- `used_by`: List of symbols using this type
- `defined_in`: MIB where type is defined
- `abstract`: Whether type is abstract

**Usage:**
```python
from app.types import TypeInfo

def process_type(type_info: TypeInfo) -> None:
    base_type = type_info.get('base_type')
    # ...
```

### `TypeRegistry`
```python
TypeRegistry = Dict[str, TypeInfo]
```
Represents the **FULL** type registry - a mapping of type names to their `TypeInfo` entries.

Example structure:
```python
{
    "Integer32": {
        "base_type": "INTEGER",
        "display_hint": None,
        "constraints": [...],
        ...
    },
    "DisplayString": {
        "base_type": "OCTET STRING",
        "display_hint": "255a",
        ...
    }
}
```

**Usage:**
```python
from app.types import TypeRegistry

def load_registry() -> TypeRegistry:
    with open("data/types.json") as f:
        return json.load(f)

def get_type(registry: TypeRegistry, type_name: str) -> TypeInfo:
    return registry.get(type_name, {})
```

### `JsonDict`
```python
JsonDict = Dict[str, Any]
```
Generic JSON-compatible dictionary type.

**Usage:**
```python
from app.types import JsonDict

def parse_config(data: JsonDict) -> None:
    # ...
```

### `OidType`
```python
OidType = Union[Tuple[int, ...], List[int]]
```
Represents SNMP Object Identifiers, which can be either tuples or lists of integers.

**Usage:**
```python
from app.types import OidType

def get_oid_value(oid: OidType) -> Any:
    # ...
```

### `TypeEncoder`
```python
TypeEncoder = Callable[[Any], Any]
```
Function signature for type encoder plugins that convert Python values to SNMP-compatible types.

**Usage:**
```python
from app.types import TypeEncoder

def create_encoder() -> TypeEncoder:
    def encoder(value: Any) -> Any:
        # encoding logic
        return encoded_value
    return encoder
```

### `DefaultValuePlugin`
```python
DefaultValuePlugin = Callable[[TypeInfo, str], Optional[Any]]
```
Function signature for default value plugins used during MIB-to-JSON generation.

**Usage:**
```python
from app.types import DefaultValuePlugin, TypeInfo

@register_plugin('my_plugin')
def my_plugin(type_info: TypeInfo, symbol_name: str) -> Optional[Any]:
    if type_info.get('base_type') == 'IpAddress':
        return '192.168.1.1'
    return None
```

## Migration Guide

### Before
```python
from typing import Dict, Any

def process_type(type_info: Dict[str, Any]) -> None:
    # ...
```

### After
```python
from app.types import TypeInfo

def process_type(type_info: TypeInfo) -> None:
    # ...
```

## Files Using These Types

- `app/base_type_handler.py` - Uses `TypeInfo` and `TypeRegistry`
- `app/default_value_plugins.py` - Uses `TypeInfo` and `DefaultValuePlugin`
- `app/type_recorder.py` - Uses `JsonDict`
- `app/table_registrar.py` - Uses `TypeInfo` and `TypeRegistry`
- `plugins/basic_types.py` - Uses `TypeInfo`
- `plugins/type_encoders.py` - Uses `TypeEncoder`

## Important Distinction

**`TypeInfo`** vs **`TypeRegistry`**:
- Use `TypeInfo` when working with a **single type's information**
- Use `TypeRegistry` when working with the **entire registry** (dict of all types)

Example:
```python
from app.types import TypeInfo, TypeRegistry

# CORRECT: Full registry
def load_types() -> TypeRegistry:
    with open("data/types.json") as f:
        return json.load(f)

# CORRECT: Single type entry
def get_base_type(type_info: TypeInfo) -> str:
    return type_info.get('base_type', '')

# CORRECT: Using both
def lookup_type(registry: TypeRegistry, name: str) -> TypeInfo:
    return registry.get(name, {})
```

## Benefits

1. **Consistency**: Single source of truth for type definitions
2. **Maintainability**: Easy to update type definitions in one place
3. **Type Safety**: Better IDE support and type checking
4. **Documentation**: Clear intent through semantic type names
5. **Refactoring**: Easier to change type definitions across the codebase

