#!/usr/bin/env python3
"""Test script to verify endPointTable is accessible via SNMP."""

import time
import subprocess
import requests

print("Starting SNMP agent with REST API...")
agent_proc = subprocess.Popen(
    ["python", "run_agent_with_rest.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

# Give it time to start and print initial output
time.sleep(5)

# Check if process is still running
if agent_proc.poll() is not None:
    print("Agent failed to start!")
    print(agent_proc.stdout.read() if agent_proc.stdout else "No output")
    exit(1)

try:
    # Test if API is accessible
    print("\nTesting API access to TEST-ENUM-MIB table schema...")

    # Get endPointTable OID: 1.3.6.1.4.1.99998.1.3
    response = requests.get(
        "http://127.0.0.1:8800/table-schema",
        params={"oid": "1.3.6.1.4.1.99998.1.3"},
        timeout=5,
    )

    if response.status_code == 200:
        schema = response.json()
        print(f"✅ Table schema retrieved: {schema['name']}")
        print(f"   Index columns: {schema['index_columns']}")
        print(f"   Instances: {schema.get('instances', [])}")
        print(f"   Columns: {list(schema['columns'].keys())}")
    else:
        print(f"❌ Failed to get table schema: {response.status_code}")
        print(response.text)

    # Try to get a value from  the table
    print("\nTesting API access to endPointName...")
    # endPointName OID: 1.3.6.1.4.1.99998.1.3.1.3
    # Instance: .192.168.1.1.1
    response = requests.get(
        "http://127.0.0.1:8800/value",
        params={"oid": "1.3.6.1.4.1.99998.1.3.1.3.192.168.1.1.1"},
        timeout=5,
    )

    if response.status_code == 200:
        value = response.json()
        print(f"✅ endPointName value: {value['value']}")
    else:
        print(f"⚠️  Could not retrieve value: {response.status_code}")
        print(response.text)

finally:
    print("\nTerminating agent...")
    agent_proc.terminate()
    agent_proc.wait(timeout=5)
    print("Done.")
