#!/usr/bin/env python3
"""Minimal SNMP agent test for debugging."""

import pytest
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
from pysnmp.proto.rfc1902 import OctetString


def test_snmp_agent_setup() -> None:
    """Test SNMP agent setup."""
    # Create SNMP engine
    snmpEngine = engine.SnmpEngine()

    # Register asyncio dispatcher
    dispatcher = AsyncioDispatcher()
    snmpEngine.register_transport_dispatcher(dispatcher)

    # Set up transport
    config.add_transport(
        snmpEngine,
        config.SNMP_UDP_DOMAIN,
        udp.UdpAsyncioTransport().open_server_mode(("127.0.0.1", 11161)),
    )
    print("Transport opened")

    # Set up community
    config.add_v1_system(snmpEngine, "public-read", "public")

    # Set up VACM for access control
    config.add_vacm_user(
        snmpEngine,
        2,  # SNMPv2c
        "public-read",
        "noAuthNoPriv",
        (1, 3, 6, 1, 2, 1),  # Allow access to .1.3.6.1.2.1 (mib-2)
        (1, 3, 6, 1, 2, 1),
    )

    # Set up context and get MIB builder from instrumentation
    snmpContext = context.SnmpContext(snmpEngine)
    mibInstrum = snmpContext.get_mib_instrum()
    mibBuilder = mibInstrum.get_mib_builder()

    # Import MIB classes
    (MibScalarInstance,) = mibBuilder.import_symbols("SNMPv2-SMI", "MibScalarInstance")

    # Register sysDescr scalar instance
    # OID for sysDescr is .1.3.6.1.2.1.1.1.0
    sysDescrInst = MibScalarInstance(
        (1, 3, 6, 1, 2, 1, 1, 1),  # Base OID (without .0)
        (0,),  # Instance suffix
        OctetString("Minimal Test Agent"),
    )

    # Export to SNMPv2-MIB module
    mibBuilder.export_symbols("SNMPv2-MIB", sysDescrInst=sysDescrInst)

    # Set up responders
    cmdrsp.GetCommandResponder(snmpEngine, snmpContext)
    cmdrsp.NextCommandResponder(snmpEngine, snmpContext)

    print("Minimal SNMP agent setup successful")
    assert snmpEngine is not None
