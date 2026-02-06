# SNMP MIB module (SNMPv2-SMI) expressed in pysnmp data model.
#
# This Python module is designed to be imported and executed by the
# pysnmp library.
#
# See https://www.pysnmp.com/pysnmp for further information.
#
# Notes
# -----
# ASN.1 source file:///Users/mintz/code/snmp-sim/data/mibs_reference/SNMPv2-SMI.txt
# Produced by pysmi-1.6.2 at Fri Feb  6 12:46:20 2026
# On host Argon.keergill.co.uk platform Darwin version 24.6.0 by user mintz
# Using Python version 3.10.14 (main, Dec 30 2025, 16:07:07) [Clang 17.0.0 (clang-1700.6.3.2)]

if 'mibBuilder' not in globals():
    import sys

    sys.stderr.write(__doc__)
    sys.exit(1)

# Import base ASN.1 objects even if this MIB does not use it

(Integer,
 OctetString,
 ObjectIdentifier) = mibBuilder.importSymbols(
    "ASN1",
    "Integer",
    "OctetString",
    "ObjectIdentifier")

(NamedValues,) = mibBuilder.importSymbols(
    "ASN1-ENUMERATION",
    "NamedValues")
(ConstraintsIntersection,
 ConstraintsUnion,
 SingleValueConstraint,
 ValueRangeConstraint,
 ValueSizeConstraint) = mibBuilder.importSymbols(
    "ASN1-REFINEMENT",
    "ConstraintsIntersection",
    "ConstraintsUnion",
    "SingleValueConstraint",
    "ValueRangeConstraint",
    "ValueSizeConstraint")

# Import SMI symbols from the MIBs this MIB depends on

(ModuleCompliance,
 NotificationGroup) = mibBuilder.importSymbols(
    "SNMPv2-CONF",
    "ModuleCompliance",
    "NotificationGroup")

(Bits,
 Counter32,
 Counter64,
 Gauge32,
 Integer32,
 IpAddress,
 ModuleIdentity,
 MibIdentifier,
 NotificationType,
 ObjectIdentity,
 MibScalar,
 MibTable,
 MibTableRow,
 MibTableColumn,
 TimeTicks,
 Unsigned32,
 iso) = mibBuilder.importSymbols(
    "SNMPv2-SMI",
    "Bits",
    "Counter32",
    "Counter64",
    "Gauge32",
    "Integer32",
    "IpAddress",
    "ModuleIdentity",
    "MibIdentifier",
    "NotificationType",
    "ObjectIdentity",
    "MibScalar",
    "MibTable",
    "MibTableRow",
    "MibTableColumn",
    "TimeTicks",
    "Unsigned32",
    "iso")

(DisplayString,
 PhysAddress,
 TextualConvention) = mibBuilder.importSymbols(
    "SNMPv2-TC",
    "DisplayString",
    "PhysAddress",
    "TextualConvention")


# MODULE-IDENTITY


# Types definitions



class ExtUTCTime(OctetString):
    """Custom type ExtUTCTime based on OctetString"""
    subtypeSpec = OctetString.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueSizeConstraint(11, 11),
        ValueSizeConstraint(13, 13),
    )





class ObjectName(ObjectIdentifier):
    """Custom type ObjectName based on ObjectIdentifier"""




class NotificationName(ObjectIdentifier):
    """Custom type NotificationName based on ObjectIdentifier"""




class Integer32(Integer32):
    """Custom type Integer32 based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueRangeConstraint(-2147483648, 2147483647),
    )





class IpAddress(OctetString):
    """Custom type IpAddress based on OctetString"""
    subtypeSpec = OctetString.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueSizeConstraint(4, 4),
    )
    fixed_length = 4





class Counter32(Integer32):
    """Custom type Counter32 based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueRangeConstraint(0, 4294967295),
    )





class Gauge32(Integer32):
    """Custom type Gauge32 based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueRangeConstraint(0, 4294967295),
    )





class Unsigned32(Integer32):
    """Custom type Unsigned32 based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueRangeConstraint(0, 4294967295),
    )





class TimeTicks(Integer32):
    """Custom type TimeTicks based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueRangeConstraint(0, 4294967295),
    )





class Opaque(OctetString):
    """Custom type Opaque based on OctetString"""




class Counter64(Integer32):
    """Custom type Counter64 based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        ValueRangeConstraint(0, 18446744073709551615),
    )




# TEXTUAL-CONVENTIONS



# MIB Managed Objects in the order of their OIDs

_ZeroDotZero_ObjectIdentity = ObjectIdentity
zeroDotZero = _ZeroDotZero_ObjectIdentity(
    (0, 0)
)
if mibBuilder.loadTexts:
    zeroDotZero.setStatus("current")
_Org_ObjectIdentity = ObjectIdentity
org = _Org_ObjectIdentity(
    (1, 3)
)
_Dod_ObjectIdentity = ObjectIdentity
dod = _Dod_ObjectIdentity(
    (1, 3, 6)
)
_Internet_ObjectIdentity = ObjectIdentity
internet = _Internet_ObjectIdentity(
    (1, 3, 6, 1)
)
_Directory_ObjectIdentity = ObjectIdentity
directory = _Directory_ObjectIdentity(
    (1, 3, 6, 1, 1)
)
_Mgmt_ObjectIdentity = ObjectIdentity
mgmt = _Mgmt_ObjectIdentity(
    (1, 3, 6, 1, 2)
)
_Mib_2_ObjectIdentity = ObjectIdentity
mib_2 = _Mib_2_ObjectIdentity(
    (1, 3, 6, 1, 2, 1)
)
_Transmission_ObjectIdentity = ObjectIdentity
transmission = _Transmission_ObjectIdentity(
    (1, 3, 6, 1, 2, 1, 10)
)
_Experimental_ObjectIdentity = ObjectIdentity
experimental = _Experimental_ObjectIdentity(
    (1, 3, 6, 1, 3)
)
_Private_ObjectIdentity = ObjectIdentity
private = _Private_ObjectIdentity(
    (1, 3, 6, 1, 4)
)
_Enterprises_ObjectIdentity = ObjectIdentity
enterprises = _Enterprises_ObjectIdentity(
    (1, 3, 6, 1, 4, 1)
)
_Security_ObjectIdentity = ObjectIdentity
security = _Security_ObjectIdentity(
    (1, 3, 6, 1, 5)
)
_SnmpV2_ObjectIdentity = ObjectIdentity
snmpV2 = _SnmpV2_ObjectIdentity(
    (1, 3, 6, 1, 6)
)
_SnmpDomains_ObjectIdentity = ObjectIdentity
snmpDomains = _SnmpDomains_ObjectIdentity(
    (1, 3, 6, 1, 6, 1)
)
_SnmpProxys_ObjectIdentity = ObjectIdentity
snmpProxys = _SnmpProxys_ObjectIdentity(
    (1, 3, 6, 1, 6, 2)
)
_SnmpModules_ObjectIdentity = ObjectIdentity
snmpModules = _SnmpModules_ObjectIdentity(
    (1, 3, 6, 1, 6, 3)
)

# Managed Objects groups


# Notification objects


# Notifications groups


# Agent capabilities


# Module compliance


# Export all MIB objects to the MIB builder

mibBuilder.exportSymbols(
    "SNMPv2-SMI",
    **{"ExtUTCTime": ExtUTCTime,
       "ObjectName": ObjectName,
       "NotificationName": NotificationName,
       "Integer32": Integer32,
       "IpAddress": IpAddress,
       "Counter32": Counter32,
       "Gauge32": Gauge32,
       "Unsigned32": Unsigned32,
       "TimeTicks": TimeTicks,
       "Opaque": Opaque,
       "Counter64": Counter64,
       "zeroDotZero": zeroDotZero,
       "org": org,
       "dod": dod,
       "internet": internet,
       "directory": directory,
       "mgmt": mgmt,
       "mib-2": mib_2,
       "transmission": transmission,
       "experimental": experimental,
       "private": private,
       "enterprises": enterprises,
       "security": security,
       "snmpV2": snmpV2,
       "snmpDomains": snmpDomains,
       "snmpProxys": snmpProxys,
       "snmpModules": snmpModules}
)
