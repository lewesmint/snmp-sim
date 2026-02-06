# SNMP Agent Integration Tests

This directory contains integration tests that verify the SNMP agent works correctly by:
1. Starting the agent in a subprocess
2. Running SNMP commands (snmpget, snmpwalk) against it
3. Verifying the responses match expectations

## Prerequisites

### SNMP Command-Line Tools

You need `net-snmp` tools installed:

**macOS (Homebrew)**:
```bash
brew install net-snmp
```

**Ubuntu/Debian**:
```bash
sudo apt-get install snmp snmp-mibs-downloader
```

**RHEL/CentOS**:
```bash
sudo yum install net-snmp-utils
```

Verify installation:
```bash
snmpget --version
snmpwalk --version
```

## Running Integration Tests

### Quick Test (Manual)

Run the integration test script directly:
```bash
python tests/test_agent_integration.py
```

This will:
- Start the SNMP agent on `127.0.0.1:11161`
- Wait for it to initialize (15 seconds)
- Run snmpget and snmpwalk commands
- Display the results
- Clean up the agent process

### Full Test Suite (pytest)

Run with pytest:
```bash
# Run all integration tests
pytest tests/test_agent_integration.py -v

# Run specific test
pytest tests/test_agent_integration.py::TestSNMPAgentIntegration::test_snmpwalk_system_group -v

# Run with output visible
pytest tests/test_agent_integration.py -v -s
```

### Test Markers

Tests are automatically skipped if SNMP tools aren't installed:
```bash
pytest tests/test_agent_integration.py -v -m "not skipif"
```

## Test Coverage

The integration tests verify:

1. **Agent Lifecycle** (`test_agent_starts_and_stops`)
   - Agent starts without errors
   - Agent responds to signals
   - Agent cleans up properly

2. **System Group** (`test_snmpwalk_system_group`, `test_snmpget_sysdescr`)
   - SNMPv2-MIB system variables (sysDescr, sysObjectID, sysUpTime, etc.)
   - Proper SNMP data types

3. **IF-MIB** (`test_snmpwalk_iftable`)
   - Interface table (`ifTable`)
   - Multiple row handling

4. **Behaviour JSON Matching** (`test_verify_behaviour_json_matches_responses`)
   - SNMP responses match behaviour JSON configuration
   - Initial values are set correctly

5. **Agent Stability** (`test_multiple_snmpget_requests`)
   - Multiple sequential requests
   - No crashes or hangs

6. **Full Walk** (`test_snmpwalk_full_tree`)
   - Walk entire MIB tree
   - Count OIDs by MIB

## Configuration

The tests use the default `agent_config.yaml` which loads:
- SNMPv2-MIB (System group)
- IF-MIB (Interface table)
- HOST-RESOURCES-MIB (Host resources)
- HOST-RESOURCES-TYPES
- CISCO-ALARM-MIB

## Timing Considerations

- **Agent startup time**: ~10-15 seconds (compiles MIBs, generates behaviour JSON)
- **snmpget timeout**: 10 seconds
- **snmpwalk timeout**: 15 seconds

If tests timeout, increase the delays in `SNMPAgentProcess.__init__()`.

## Troubleshooting

### Agent fails to start

Check stderr output:
```python
with SNMPAgentProcess() as agent:
    if agent.process:
        stdout, stderr = agent.process.communicate()
        print(stderr)
```

Common issues:
- Port 11161 already in use
- Missing MIB files
- Invalid agent_config.yaml

### No response from agent

1. Verify agent is listening:
   ```bash
   lsof -i :11161
   ```

2. Try direct snmpget:
   ```bash
   snmpget -v 2c -c public 127.0.0.1:11161 .1.3.6.1.2.1.1.1.0
   ```

3. Check agent logs:
   ```bash
   tail -f logs/snmp-agent.log
   ```

### Timeouts

If agent takes longer to start, increase `startup_delay`:
```python
with SNMPAgentProcess(startup_delay=20.0) as agent:
    ...
```

## Example Output

```
Starting SNMP Agent Integration Test...
============================================================
Waiting 15.0s for agent to start...
Agent process running (PID: 12345)
✓ Agent started on 127.0.0.1:11161

Testing sysDescr...
✓ sysDescr: SNMPv2-MIB::sysDescr.0 = STRING: "Simple Python SNMP Agent - Demo System"

Testing system group walk...
✓ Got 7 system variables

First 10 results:
  1. SNMPv2-MIB::sysDescr.0 = STRING: "Simple Python SNMP Agent - Demo System"
  2. SNMPv2-MIB::sysObjectID.0 = OID: SNMPv2-SMI::enterprises.99999
  3. SNMPv2-MIB::sysUpTime.0 = Timeticks: (123) 0:00:01.23
  4. SNMPv2-MIB::sysContact.0 = STRING: "Admin <admin@example.com>"
  5. SNMPv2-MIB::sysName.0 = STRING: "my-pysnmp-agent"
  6. SNMPv2-MIB::sysLocation.0 = STRING: "Development Lab"
  7. SNMPv2-MIB::sysServices.0 = INTEGER: 0

============================================================
✓ All tests passed!
```

## CI/CD Integration

For CI environments without SNMP tools, tests will be automatically skipped:
```bash
pytest tests/test_agent_integration.py -v
# Output: SKIPPED [1] snmpget command not available - install net-snmp tools
```

To force running in CI:
```bash
# .github/workflows/test.yml
- name: Install SNMP tools
  run: |
    sudo apt-get update
    sudo apt-get install -y snmp
- name: Run integration tests
  run: pytest tests/test_agent_integration.py -v
```
