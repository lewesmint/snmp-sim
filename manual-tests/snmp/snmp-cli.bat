@echo off
REM SNMP CLI Test Script for Windows
REM
REM Usage:
REM   snmp-get.bat <host[:port]> <oid>
REM   snmp-set.bat <host[:port]> <oid> <type> <value>
REM   snmp-walk.bat <host[:port]> <oid>
REM   snmp-test.bat <host[:port]> [--base-oid <oid>] [--index-ip <ip>] [--index-port <port>]
REM
REM Examples:
REM   snmp-get.bat localhost:11161 1.3.6.1.2.1.1.5.0
REM   snmp-set.bat localhost:11161 1.3.6.1.4.1.4045.750829.1.1.1.4.127.0.0.1.2000 i 4
REM   snmp-test.bat localhost:11161

setlocal enabledelayedexpansion
cd /d "%~dp0"

if "%~1"=="" (
    echo SNMP CLI Test Suite for Windows
    echo.
    echo Available commands:
    echo   snmp-get.bat ^<host[:port]^> ^<oid^>
    echo   snmp-set.bat ^<host[:port]^> ^<oid^> ^<type^> ^<value^>
    echo   snmp-walk.bat ^<host[:port]^> ^<oid^>
    echo   snmp-test.bat ^<host[:port]^> [options]
    echo.
    echo Run individual scripts for help, e.g.:
    echo   python snmp_cli_test.py --help
    goto :eof
)

python snmp_cli_test.py %*
