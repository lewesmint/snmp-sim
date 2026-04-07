# SNMP CLI Testing Guide for Windows

## Quick Start

The test suite provides command-line SNMP operations that work on Windows without needing external Net-SNMP binaries.

### Available Scripts

**Batch file (cmd.exe):**
```
snmp-cli.bat <command> [args...]
```

**PowerShell:**
```
.\snmp-cli.ps1 <command> [args...]
```

**Direct Python:**
```
python snmp_cli_test.py <command> [args...]
```

## Commands

### GET - Read a single OID

```batch
snmp-cli.bat get localhost:11161 1.3.6.1.2.1.1.5.0
```

```powershell
.\snmp-cli.ps1 get localhost:11161 1.3.6.1.2.1.1.5.0
```

### SET - Write to an OID

Value types:
- `i` = Integer
- `o` = OctetString  
- `s` = String
- `c` = Counter32

**Example: SET RowStatus to createAndGo (value 4):**

```batch
snmp-cli.bat set localhost:11161 1.3.6.1.4.1.8998.321654.1.1.1.4.127.0.0.1.2000 i 4
```

```powershell
.\snmp-cli.ps1 set localhost:11161 1.3.6.1.4.1.8998.321654.1.1.1.4.127.0.0.1.2000 i 4
```

### WALK - Browse an OID subtree

```batch
snmp-cli.bat walk localhost:11161 1.3.6.1.4.1.8998.321654
```

```powershell
.\snmp-cli.ps1 walk localhost:11161 1.3.6.1.4.1.8998.321654
```

### TEST-WORKFLOW - Run full createAndGo/destroy test

**Using default FOOBAR OIDs:**

```batch
snmp-cli.bat test-workflow localhost:11161
```

```powershell
.\snmp-cli.ps1 test-workflow localhost:11161
```

**Using custom OIDs (for your extracted MIB):**

```batch
snmp-cli.bat test-workflow localhost:11161 ^
    --base-oid 1.3.6.1.4.1.YOUR.OID.1.1.1 ^
    --index-ip 127.0.0.1 ^
    --index-port 2000
```

```powershell
.\snmp-cli.ps1 test-workflow localhost:11161 `
    --base-oid 1.3.6.1.4.1.YOUR.OID.1.1.1 `
    --index-ip 127.0.0.1 `
    --index-port 2000
```

## Full Workflow Example (FOOBAR MIB)

Open Command Prompt or PowerShell and run:

```batch
REM 1. Test initial system
snmp-cli.bat get localhost:11161 1.3.6.1.2.1.1.5.0

REM 2. Create a new row (createAndGo = 4)
snmp-cli.bat set localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000 i 4

REM 3. Verify row is active (should return 1 = active)
snmp-cli.bat get localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000

REM 4. Check trap port got DEFVAL (should be 162)
snmp-cli.bat get localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.3.127.0.0.1.2000

REM 5. Walk entire row
snmp-cli.bat walk localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.127.0.0.1.2000

REM 6. Destroy the row (destroy = 6)
snmp-cli.bat set localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000 i 6

REM 7. Verify row is gone (should get error)
snmp-cli.bat get localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000
```

PowerShell equivalent:

```powershell
# 1. Test initial system
.\snmp-cli.ps1 get localhost:11161 1.3.6.1.2.1.1.5.0

# 2. Create a new row (createAndGo = 4)
.\snmp-cli.ps1 set localhost:11161 1.3.6.1.4.1.8998.321654.1.1.1.4.127.0.0.1.2000 i 4

# 3. Verify row is active (should return 1 = active)
.\snmp-cli.ps1 get localhost:11161 1.3.6.1.4.1.8998.321654.1.1.1.4.127.0.0.1.2000

# 4. Check trap port got DEFVAL (should be 162)
.\snmp-cli.ps1 get localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.3.127.0.0.1.2000

# 5. Walk entire row
.\snmp-cli.ps1 walk localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.127.0.0.1.2000

# 6. Destroy the row (destroy = 6)
.\snmp-cli.ps1 set localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000 i 6

# 7. Verify row is gone (should get error)
.\snmp-cli.ps1 get localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000
```

## RowStatus Values

| Value | Name | Meaning |
|-------|------|---------|
| 0 | notExists | Row doesn't exist |
| 1 | active | Row exists and is active |
| 2 | notInService | Row exists but is not in service |
| 3 | notReady | Row exists but isn't ready |
| 4 | createAndGo | Create and immediately activate |
| 5 | createAndWait | Create but don't activate |
| 6 | destroy | Delete the row |

## Customizing for Your MIB

If you've extracted OIDs from a different MIB, identify:

1. **Base OID** of the table row (e.g., `1.3.6.1.4.1.YOURCOMPANY.1.2.1`)
2. **Column OIDs** for:
   - Index columns (e.g., IP address, port)
   - RowStatus column (usually the last column, e.g., `.4`)
   - Data columns (e.g., trap port at `.3`)

Then run the test with custom OIDs:

```batch
snmp-cli.bat test-workflow localhost:11161 ^
    --base-oid 1.3.6.1.4.1.YOUR.OID.1.2.1 ^
    --index-ip 10.0.0.1 ^
    --index-port 5000
```

## Troubleshooting

**Connection refused?**
- Ensure agent is running: `python run_agent_with_rest.py`
- Check port: default is UDP 11161, not 161

**"No Such Instance" on GET?**
- Verify the OID is correct for your MIB
- Try WALK to see available OIDs

**SET returns error?**
- Check value type (i for integer, s for string, etc.)
- Verify RowStatus constraints

## Running from Windows Explorer

Create a batch file `run-test.bat` in the test directory:

```batch
@echo off
cd /d "%~dp0"
python snmp_cli_test.py test-workflow localhost:11161 %*
pause
```

Double-click to run, or add command-line arguments.
