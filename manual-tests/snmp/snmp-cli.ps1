# PowerShell wrapper for SNMP CLI tests
# Usage: .\snmp-cli.ps1 <command> [args...]
# 
# Examples:
#   .\snmp-cli.ps1 get localhost:11161 1.3.6.1.2.1.1.5.0
#   .\snmp-cli.ps1 set localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000 i 4
#   .\snmp-cli.ps1 test-workflow localhost:11161

param(
    [string]$Command,
    [string[]]$Arguments
)

if (-not $Command) {
    Write-Host "SNMP CLI Test Suite for PowerShell"
    Write-Host ""
    Write-Host "Available commands:"
    Write-Host "  get <host[:port]> <oid>"
    Write-Host "  set <host[:port]> <oid> <type> <value>"
    Write-Host "  walk <host[:port]> <oid>"
    Write-Host "  test-workflow <host[:port]> [--base-oid <oid>] [--index-ip <ip>] [--index-port <port>]"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\snmp-cli.ps1 get localhost:11161 1.3.6.1.2.1.1.5.0"
    Write-Host "  .\snmp-cli.ps1 set localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000 i 4"
    Write-Host "  .\snmp-cli.ps1 test-workflow localhost:11161"
    exit 0
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "snmp_cli_test.py"

$AllArgs = @($Command) + $Arguments
python $PythonScript @AllArgs
