# BaseTypeHandler - Clean Type System Implementation

## ✅ Completed

### Architecture
Created a clean type system that follows SMIv2 RFC 2578 spec:
- **Only 3 hardcoded types**: INTEGER, OCTET STRING, OBJECT IDENTIFIER
- **All other types resolved from type registry**: Integer32, Counter32, IpAddress, DisplayString, BITS, etc.

### Files Created
1. **`app/base_type_handler.py`** - Core type handler
   - `resolve_to_base_type()` - Resolve any type to its base ASN.1 type
   - `get_default_value()` - Get sensible defaults for any type
   - `create_pysnmp_value()` - Create PySNMP value objects
   - `validate_value()` - Validate values against type constraints
   - `get_type_info()` - Query type registry

2. **`examples/base_type_handler_usage.py`** - Usage examples

### Files Updated
1. **`app/table_registrar.py`**
   - Now uses BaseTypeHandler instead of hardcoded type logic
   - Removed 70+ lines of hardcoded type handling
   - Added type_registry parameter to constructor

2. **`app/api.py`**
   - Added `/type-info/{type_name}` endpoint
   - Added `/types` endpoint to list all types
   - Existing `/validate-types` endpoint

### Old Files (Moved to retired/)
- `retired/snmp_type_initializer.py` - Old implementation with hardcoded types

## Key Benefits

### 1. **Correctness**
Aligns with SMIv2 specification - only base types are hardcoded

### 2. **Extensibility**  
Any TEXTUAL-CONVENTION automatically works once in types.json:
```python
handler.get_default_value('CiscoAlarmSeverity')  # Works!
handler.get_default_value('MyCustomTC')          # Works!
```

### 3. **Maintainability**
No scattered hardcoded type lists. Single source of truth (types.json).

### 4. **API Access**
```bash
# Get info about any type
GET /type-info/Integer32
GET /type-info/DisplayString
GET /type-info/CiscoAlarmSeverity

# List all available types
GET /types

# Validate type registry
GET /validate-types
```

## Usage Examples

### Basic Usage
```python
from app.base_type_handler import BaseTypeHandler

handler = BaseTypeHandler()

# Get default values
handler.get_default_value('Integer32')       # 0
handler.get_default_value('IpAddress')       # '0.0.0.0'
handler.get_default_value('DisplayString')   # ''

# Resolve to base types
handler.resolve_to_base_type('Counter64')    # 'INTEGER'
handler.resolve_to_base_type('IpAddress')    # 'OCTET STRING'

# Create PySNMP values
value = handler.create_pysnmp_value('Integer32', 100, mib_builder)

# Validate
handler.validate_value('Integer32', 42)      # True
handler.validate_value('Integer32', 'abc')   # False
```

### With Table Registration
```python
from app.table_registrar import TableRegistrar
from app.base_type_handler import BaseTypeHandler

# Type registry is automatically used
registrar = TableRegistrar(
    mib_builder=mib_builder,
    mib_scalar_instance=MibScalarInstance,
    mib_table=MibTable,
    mib_table_row=MibTableRow,
    mib_table_column=MibTableColumn,
    logger=logger,
    type_registry=type_registry  # Optional - loaded from data/types.json if not provided
)
```

## Future Enhancements

### Phase 1 (Current) ✅
- Clean BaseTypeHandler with 3 base types only
- Integration with table_registrar
- API endpoints for type info

### Phase 2 (Next)
- Enhance type_recorder.py to capture `base_asn1_type` explicitly
- Add `application_tag` to type registry for Counter32, Gauge32, etc.
- Rebuild types.json with enhanced metadata

### Phase 3 (Future)
- Add constraint validation (range, size)
- Add enum validation
- Support for BITS encoding/decoding
- Performance optimization with type caching

## Testing

Run the example:
```bash
python examples/base_type_handler_usage.py
```

Test via API:
```bash
# Terminal 1
python run_agent_with_rest.py

# Terminal 2
curl http://localhost:8000/types
curl http://localhost:8000/type-info/Integer32
curl http://localhost:8000/type-info/IpAddress
curl http://localhost:8000/validate-types
```

## Migration Notes

### For New Code
Always use BaseTypeHandler:
```python
from app.base_type_handler import BaseTypeHandler

handler = BaseTypeHandler()
default = handler.get_default_value(type_name)
```

### For Existing Code
If you see hardcoded type checks like:
```python
if type_name in ['Integer32', 'Counter32', 'Gauge32']:
    # ...
```

Replace with:
```python
from app.base_type_handler import BaseTypeHandler

handler = BaseTypeHandler()
base_type = handler.resolve_to_base_type(type_name)
if base_type == 'INTEGER':
    # ...
```

## Architecture Principles

1. **Only 3 types are fundamental** - INTEGER, OCTET STRING, OBJECT IDENTIFIER
2. **Everything else is derived** - Resolved from type registry at runtime
3. **Single source of truth** - types.json contains all type metadata
4. **No hardcoded type lists** - Extensible to any TEXTUAL-CONVENTION
5. **Clean separation** - Type logic in one place, not scattered
