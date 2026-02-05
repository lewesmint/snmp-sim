#!/usr/bin/env python3
"""Minimal SNMP agent test for debugging."""

import logging
from pysnmp import debug as pysnmp_debug
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.smi import builder

# Enable PySNMP debugging
pysnmp_debug.setLogger(pysnmp_debug.Debug('all'))
logging.basicConfig(level=logging.DEBUG)

# Create SNMP engine
snmpEngine = engine.SnmpEngine()

# Get MIB builder
mibBuilder = snmpEngine.get_mib_builder()
mibBuilder.add_mib_sources(builder.DirMibSource('compiled-mibs'))

# Import MIB classes
(MibScalar, MibScalarInstance, MibTable, MibTableRow, MibTableColumn) = mibBuilder.import_symbols(
    'SNMPv2-SMI',
    'MibScalar',
    'MibScalarInstance',
    'MibTable',
    'MibTableRow',
    'MibTableColumn'
)

# Set up transport
try:
    transport = udp.UdpTransport().open_server_mode(("127.0.0.1", 11161))
    config.add_transport(snmpEngine, udp.DOMAIN_NAME, transport)
    print("Transport opened")
except Exception as e:
    print(f"Failed to open transport: {e}")

# Set up community
config.add_v1_system(snmpEngine, "public", "public")

# Set up responders
snmpContext = context.SnmpContext(snmpEngine)
cmdrsp.GetCommandResponder(snmpEngine, snmpContext)
cmdrsp.NextCommandResponder(snmpEngine, snmpContext)

# Load SNMPv2-MIB which already has sysDescr defined
print("Loading SNMPv2-MIB...")
mibBuilder.load_modules('SNMPv2-MIB')
print("SNMPv2-MIB loaded")

# Import the existing sysDescr object
print("Importing sysDescr...")
(sysDescr,) = mibBuilder.import_symbols('SNMPv2-MIB', 'sysDescr')
print(f"sysDescr imported: {sysDescr}, OID: {sysDescr.name}")

# Import DisplayString type
DisplayString = mibBuilder.import_symbols('SNMPv2-TC', 'DisplayString')[0]

# Create an instance with our value
print("Creating sysDescr instance...")
sysDescrInst = MibScalarInstance(
    sysDescr.name,
    (0,),
    DisplayString("Minimal Test Agent")
)
print(f"Instance created: {sysDescrInst}")

# Export the instance
print("Exporting instance...")
mibBuilder.export_symbols('SNMPv2-MIB', sysDescrInst=sysDescrInst)
print("Instance exported")

# Debug: Check what's in the MIB
print(f"\nMIB symbols in SNMPv2-MIB: {list(mibBuilder.mibSymbols.get('SNMPv2-MIB', {}).keys())[:10]}...")

print("Minimal SNMP agent running on 127.0.0.1:11161")
print("Test with: snmpget -c public -v2c localhost:11161 sysDescr.0")

# Run the dispatcher
try:
    snmpEngine.transport_dispatcher.job_started(1)
    snmpEngine.open_dispatcher()
    print("Dispatcher opened")
    snmpEngine.transport_dispatcher.run_dispatcher()
except KeyboardInterrupt:
    print("Shutting down")
finally:
    snmpEngine.close_dispatcher()