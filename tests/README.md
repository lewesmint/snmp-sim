# Test Organization

This directory contains all tests for the SNMP simulator, organized by type and module.

## Structure

```
tests/
├── unit/              # Unit tests for individual modules
│   ├── agent/         # SNMP agent and transport tests (8 files)
│   ├── cli/           # CLI command tests (6 files)
│   ├── mib/           # MIB compilation and registration tests (6 files)
│   ├── plugin_tests/  # Plugin system tests (3 files)
│   ├── table/         # Table handling tests (3 files)
│   ├── trap/          # TRAP sender and receiver tests (2 files)
│   └── type_system/   # Type registry and recording tests (8 files)
│
├── integration/       # Integration tests (10 files)
│   ├── test_trap_integration.py
│   ├── test_agent.py
│   ├── test_datetime_update.py
│   ├── test_fixes.py
│   ├── test_integration_getnext.py
│   ├── test_schema_integration.py
│   ├── test_value_decoding.py
│   └── unit/
│       ├── test_simple_table_getnext.py
│       ├── test_table_getnext.py
│       └── test_table_practical.py
│
├── misc/              # Miscellaneous and utility tests (9 files)
│   ├── test_api.py
│   ├── test_agent_registration.py
│   ├── test_basic_models.py
│   ├── test_compile_mib.py
│   ├── test_coverage_gaps.py
│   ├── test_dynamic_mib_controller.py
│   ├── test_generator_more.py
│   ├── test_schema_loader.py
│   └── test_syntax_resolver.py
│

## Test Categories

### Unit Tests (36 files)

#### Agent Tests (`unit/agent/`)
- `test_snmp_agent_unit.py` - Core agent functionality
- `test_snmp_agent_more.py` - Additional agent features
- `test_snmp_agent_additional.py` - Extended agent tests
- `test_agent_errors.py` - Error handling
- `test_snmp_table_responder.py` - Table response handling
- `test_snmp_transport_unit.py` - Transport layer
- `test_snmp_transport_more.py` - Additional transport tests
- `test_my_pysnmp_agent.py` - PySNMP agent integration

#### CLI Tests (`unit/cli/`)
- `test_cli_build_model.py` - Model building commands
- `test_cli_compile_mib_unit.py` - MIB compilation
- `test_cli_load_model.py` - Model loading
- `test_cli_register_types.py` - Type registration
- `test_cli_run_agent.py` - Agent execution
- `test_cli_scripts.py` - CLI script tests

#### MIB Tests (`unit/mib/`)
- `test_mib_registrar.py` - MIB registration
- `test_mib_registrar_more.py` - Additional registrar tests
- `test_mib_registry_unit.py` - Registry functionality
- `test_mib_registry_more.py` - Extended registry tests
- `test_mib_to_json.py` - JSON conversion
- `test_compiler_unit.py` - MIB compilation

#### Plugin Tests (`unit/plugin_tests/`)
- `test_plugin_loader.py` - Plugin loading mechanism
- `test_plugins.py` - Plugin functionality
- `test_default_value_plugins.py` - Default value generation

#### Table Tests (`unit/table/`)
- `test_table_registrar.py` - Table registration
- `test_table_registration.py` - Registration process
- `test_tc_table_walking.py` - Table walking operations

#### Trap Tests (`unit/trap/`)
- `test_trap_sender.py` - Trap transmission
- `test_trap_receiver.py` - Trap reception

#### Type System Tests (`unit/type_system/`)
- `test_type_recorder_unit.py` - Type recording
- `test_type_recorder_more.py` - Extended recording tests
- `test_type_recorder_build.py` - Type building
- `test_type_registry.py` - Registry operations
- `test_type_registry_loading.py` - Registry loading
- `test_type_registry_validator.py` - Validation
- `test_base_type_handler.py` - Base type handling
- `test_base_type_handler_more.py` - Extended type handling

### Integration Tests (10 files)
End-to-end tests that verify multiple components working together.

### Miscellaneous Tests (9 files)
API tests, utility tests, and other cross-cutting concerns.

## Running Tests

```bash
# Run all tests
pytest tests/

# Run specific category
pytest tests/unit/trap/
pytest tests/integration/
pytest tests/misc/

# Run specific module tests
pytest tests/unit/agent/
pytest tests/unit/mib/

# Run a specific test file
pytest tests/unit/trap/test_trap_sender.py
```

## Manual Tests

Interactive and manual test scripts have been moved to the `manual-tests/` directory at the project root to prevent pytest from attempting to collect and run them. These scripts are meant to be executed directly:

- `manual-tests/ui/` - GUI/Tkinter test scripts (12 files)
- `manual-tests/snmp/` - SNMP operation test scripts (8 files)
- `manual-tests/oid/` - OID utility test scripts (5 files)
- `manual-tests/mib/` - MIB exploration scripts (5 files)

See `manual-tests/README.md` for more information on running these scripts.
## Total Test Count
**576 tests** across 55 test files
