# SNMP MIB module (CISCO-ALARM-MIB) expressed in pysnmp data model.
#
# This Python module is designed to be imported and executed by the
# pysnmp library.
#
# See https://www.pysnmp.com/pysnmp for further information.
#
# Notes
# -----
# ASN.1 source file:///Users/mintz/code/snmp-sim/data/mibs/cisco/CISCO-ALARM-MIB.my
# Produced by pysmi-1.6.2 at Fri Feb  6 12:46:22 2026
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

(ciscoMgmt,) = mibBuilder.importSymbols(
    "CISCO-SMI",
    "ciscoMgmt")

(EntPhysicalIndexOrZero,) = mibBuilder.importSymbols(
    "CISCO-TC",
    "EntPhysicalIndexOrZero")

(InterfaceIndexOrZero,) = mibBuilder.importSymbols(
    "IF-MIB",
    "InterfaceIndexOrZero")

(ModuleCompliance,
 NotificationGroup,
 ObjectGroup) = mibBuilder.importSymbols(
    "SNMPv2-CONF",
    "ModuleCompliance",
    "NotificationGroup",
    "ObjectGroup")

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
 TextualConvention,
 TimeStamp,
 TruthValue) = mibBuilder.importSymbols(
    "SNMPv2-TC",
    "DisplayString",
    "PhysAddress",
    "TextualConvention",
    "TimeStamp",
    "TruthValue")


# MODULE-IDENTITY

ciscoAlarmMIB = ModuleIdentity(
    (1, 3, 6, 1, 4, 1, 9, 9, 869)
)
if mibBuilder.loadTexts:
    ciscoAlarmMIB.setRevisions(
        ("2021-05-17 00:00",
         "2019-08-28 00:00",
         "2019-08-28 00:00")
    )


# Types definitions


# TEXTUAL-CONVENTIONS



class CoiAlarmObjectTypeClass(TextualConvention, Integer32):
    status = "current"
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        SingleValueConstraint(
            *(1,
              2,
              3,
              4,
              5,
              6,
              7,
              8,
              9,
              10,
              11,
              12,
              13,
              14,
              15,
              16,
              17,
              18,
              19,
              20,
              21,
              22,
              23,
              24,
              25,
              26,
              27,
              28,
              29,
              30,
              31,
              32,
              33,
              34,
              35,
              36,
              37,
              38,
              39,
              40,
              41,
              42,
              43,
              44,
              45,
              46,
              47,
              48,
              49,
              50,
              51,
              52,
              53,
              54,
              55,
              56,
              57,
              58,
              59,
              60,
              61,
              62,
              63,
              64,
              65,
              66,
              67,
              68)
        )
    )
    namedValues = NamedValues(
        *(("unknown", 1),
          ("hwMemorySbe", 2),
          ("hwMemoryMbe", 3),
          ("hwMemoryParity", 4),
          ("hwFreeze", 5),
          ("hwFlopError", 6),
          ("hwInternal", 7),
          ("hwTimeout", 8),
          ("hwHang", 9),
          ("hwError", 10),
          ("hwLinkCrc", 11),
          ("hwCodeViolation", 12),
          ("hwLinkDisparity", 13),
          ("hwEnvmonSensorAlarm", 14),
          ("hwEnvmonPemAlarm", 15),
          ("hwEnvmonFanAlarm", 16),
          ("swMemoryFault", 17),
          ("swBusError", 18),
          ("swProcessCrash", 19),
          ("swMallocError", 20),
          ("swFoobar", 21),
          ("swConnectFail", 22),
          ("swProcessRestart", 23),
          ("swProcessFailure", 24),
          ("swMandatoryProcessFailure", 25),
          ("swServiceRestart", 26),
          ("swServiceFailure", 27),
          ("swPmHeartbeat", 28),
          ("swHostosHeartbeat", 29),
          ("swCccWdog", 30),
          ("hwConfigErr", 31),
          ("hwGenericErr", 32),
          ("hwIndirectErr", 33),
          ("hwOorThreshErr", 34),
          ("hwUnexpectedErr", 35),
          ("hwBoardReload", 36),
          ("hwSliceReload", 37),
          ("hwMiscErr", 38),
          ("hwRxResourceErr", 39),
          ("hwTxResourceErr", 40),
          ("hwLinkStatChange", 41),
          ("hwEtherBridge", 42),
          ("swInitErr", 43),
          ("swMiscErr", 44),
          ("hwEnvmonEcuAlarm", 45),
          ("hwEnvmonPwrFilterAlarm", 46),
          ("hwSonet", 47),
          ("hwG709", 48),
          ("hwEthernet", 49),
          ("hwOptics", 50),
          ("hwGfp", 51),
          ("hwSdhController", 52),
          ("swFsdbaggPlane", 53),
          ("hwOts", 54),
          ("swMacsecMka", 55),
          ("swSmartLicErr", 56),
          ("swProvisionErr", 57),
          ("hwSyncec", 58),
          ("hwPci", 59),
          ("swWdDiskUsage", 60),
          ("swCfgmgr", 61),
          ("swG709Otnsec", 62),
          ("hwCpri", 63),
          ("hwImfpga", 64),
          ("swFsdbaggConnMismatch", 65),
          ("hwFibreChannel", 66),
          ("hwE1", 67),
          ("hwCem", 68))
    )



# MIB Managed Objects in the order of their OIDs

_CiscoAlarmMIBNotifs_ObjectIdentity = ObjectIdentity
ciscoAlarmMIBNotifs = _CiscoAlarmMIBNotifs_ObjectIdentity(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 0)
)
_CiscoAlarmMIBObjects_ObjectIdentity = ObjectIdentity
ciscoAlarmMIBObjects = _CiscoAlarmMIBObjects_ObjectIdentity(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1)
)
_CoiAlarmActive_ObjectIdentity = ObjectIdentity
coiAlarmActive = _CoiAlarmActive_ObjectIdentity(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1)
)
_CoiAlarmActiveTable_Object = MibTable
coiAlarmActiveTable = _CoiAlarmActiveTable_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1)
)
if mibBuilder.loadTexts:
    coiAlarmActiveTable.setStatus("current")
_CoiAlarmActiveEntry_Object = MibTableRow
coiAlarmActiveEntry = _CoiAlarmActiveEntry_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1)
)
coiAlarmActiveEntry.setIndexNames(
    (0, "CISCO-ALARM-MIB", "coiAlarmIndex"),
    (0, "CISCO-ALARM-MIB", "coiAlarmObjectIfIndex"),
    (0, "CISCO-ALARM-MIB", "coiAlarmObjectEntPhyIndex"),
    (0, "CISCO-ALARM-MIB", "coiAlarmType"),
)
if mibBuilder.loadTexts:
    coiAlarmActiveEntry.setStatus("current")
_CoiAlarmIndex_Type = Integer32
_CoiAlarmIndex_Object = MibTableColumn
coiAlarmIndex = _CoiAlarmIndex_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 1),
    _CoiAlarmIndex_Type()
)
coiAlarmIndex.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmIndex.setStatus("current")
_CoiAlarmObjectIfIndex_Type = InterfaceIndexOrZero
_CoiAlarmObjectIfIndex_Object = MibTableColumn
coiAlarmObjectIfIndex = _CoiAlarmObjectIfIndex_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 2),
    _CoiAlarmObjectIfIndex_Type()
)
coiAlarmObjectIfIndex.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmObjectIfIndex.setStatus("current")
_CoiAlarmObjectEntPhyIndex_Type = EntPhysicalIndexOrZero
_CoiAlarmObjectEntPhyIndex_Object = MibTableColumn
coiAlarmObjectEntPhyIndex = _CoiAlarmObjectEntPhyIndex_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 3),
    _CoiAlarmObjectEntPhyIndex_Type()
)
coiAlarmObjectEntPhyIndex.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmObjectEntPhyIndex.setStatus("current")
_CoiAlarmObjectName_Type = DisplayString
_CoiAlarmObjectName_Object = MibTableColumn
coiAlarmObjectName = _CoiAlarmObjectName_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 4),
    _CoiAlarmObjectName_Type()
)
coiAlarmObjectName.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmObjectName.setStatus("current")
_CoiAlarmObjectType_Type = CoiAlarmObjectTypeClass
_CoiAlarmObjectType_Object = MibTableColumn
coiAlarmObjectType = _CoiAlarmObjectType_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 5),
    _CoiAlarmObjectType_Type()
)
coiAlarmObjectType.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmObjectType.setStatus("current")
_CoiAlarmType_Type = DisplayString
_CoiAlarmType_Object = MibTableColumn
coiAlarmType = _CoiAlarmType_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 6),
    _CoiAlarmType_Type()
)
coiAlarmType.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmType.setStatus("current")
_CoiAlarmTimeStamp_Type = Counter64
_CoiAlarmTimeStamp_Object = MibTableColumn
coiAlarmTimeStamp = _CoiAlarmTimeStamp_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 7),
    _CoiAlarmTimeStamp_Type()
)
coiAlarmTimeStamp.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmTimeStamp.setStatus("current")


class _CoiAlarmSeverity_Type(Integer32):
    """Custom type coiAlarmSeverity based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        SingleValueConstraint(
            *(0,
              1,
              2,
              3,
              4,
              5)
        )
    )
    namedValues = NamedValues(
        *(("unknown", 0),
          ("notReported", 1),
          ("notAlarmed", 2),
          ("minor", 3),
          ("major", 4),
          ("critical", 5))
    )


_CoiAlarmSeverity_Type.__name__ = "Integer32"
_CoiAlarmSeverity_Object = MibTableColumn
coiAlarmSeverity = _CoiAlarmSeverity_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 8),
    _CoiAlarmSeverity_Type()
)
coiAlarmSeverity.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmSeverity.setStatus("current")


class _CoiAlarmStatus_Type(Integer32):
    """Custom type coiAlarmStatus based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        SingleValueConstraint(
            *(0,
              1,
              2,
              3)
        )
    )
    namedValues = NamedValues(
        *(("unknown", 0),
          ("set", 1),
          ("clear", 2),
          ("suppress", 3))
    )


_CoiAlarmStatus_Type.__name__ = "Integer32"
_CoiAlarmStatus_Object = MibTableColumn
coiAlarmStatus = _CoiAlarmStatus_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 9),
    _CoiAlarmStatus_Type()
)
coiAlarmStatus.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmStatus.setStatus("current")


class _CoiAlarmServiceAffecting_Type(Integer32):
    """Custom type coiAlarmServiceAffecting based on Integer32"""
    subtypeSpec = Integer32.subtypeSpec
    subtypeSpec += ConstraintsUnion(
        SingleValueConstraint(
            *(0,
              1,
              2)
        )
    )
    namedValues = NamedValues(
        *(("unknown", 0),
          ("notServiceAffecting", 1),
          ("serviceAffecting", 2))
    )


_CoiAlarmServiceAffecting_Type.__name__ = "Integer32"
_CoiAlarmServiceAffecting_Object = MibTableColumn
coiAlarmServiceAffecting = _CoiAlarmServiceAffecting_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 10),
    _CoiAlarmServiceAffecting_Type()
)
coiAlarmServiceAffecting.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmServiceAffecting.setStatus("current")
_CoiAlarmDescription_Type = DisplayString
_CoiAlarmDescription_Object = MibTableColumn
coiAlarmDescription = _CoiAlarmDescription_Object(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 1, 1, 1, 1, 11),
    _CoiAlarmDescription_Type()
)
coiAlarmDescription.setMaxAccess("read-only")
if mibBuilder.loadTexts:
    coiAlarmDescription.setStatus("current")

# Managed Objects groups


# Notification objects

coiAlarmStatusChange = NotificationType(
    (1, 3, 6, 1, 4, 1, 9, 9, 869, 0, 1)
)
coiAlarmStatusChange.setObjects(
      *(("CISCO-ALARM-MIB", "coiAlarmIndex"),
        ("CISCO-ALARM-MIB", "coiAlarmObjectIfIndex"),
        ("CISCO-ALARM-MIB", "coiAlarmObjectEntPhyIndex"),
        ("CISCO-ALARM-MIB", "coiAlarmObjectName"),
        ("CISCO-ALARM-MIB", "coiAlarmType"),
        ("CISCO-ALARM-MIB", "coiAlarmSeverity"),
        ("CISCO-ALARM-MIB", "coiAlarmStatus"),
        ("CISCO-ALARM-MIB", "coiAlarmDescription"))
)
if mibBuilder.loadTexts:
    coiAlarmStatusChange.setStatus(
        "current"
    )


# Notifications groups


# Agent capabilities


# Module compliance


# Export all MIB objects to the MIB builder

mibBuilder.exportSymbols(
    "CISCO-ALARM-MIB",
    **{"CoiAlarmObjectTypeClass": CoiAlarmObjectTypeClass,
       "ciscoAlarmMIB": ciscoAlarmMIB,
       "ciscoAlarmMIBNotifs": ciscoAlarmMIBNotifs,
       "coiAlarmStatusChange": coiAlarmStatusChange,
       "ciscoAlarmMIBObjects": ciscoAlarmMIBObjects,
       "coiAlarmActive": coiAlarmActive,
       "coiAlarmActiveTable": coiAlarmActiveTable,
       "coiAlarmActiveEntry": coiAlarmActiveEntry,
       "coiAlarmIndex": coiAlarmIndex,
       "coiAlarmObjectIfIndex": coiAlarmObjectIfIndex,
       "coiAlarmObjectEntPhyIndex": coiAlarmObjectEntPhyIndex,
       "coiAlarmObjectName": coiAlarmObjectName,
       "coiAlarmObjectType": coiAlarmObjectType,
       "coiAlarmType": coiAlarmType,
       "coiAlarmTimeStamp": coiAlarmTimeStamp,
       "coiAlarmSeverity": coiAlarmSeverity,
       "coiAlarmStatus": coiAlarmStatus,
       "coiAlarmServiceAffecting": coiAlarmServiceAffecting,
       "coiAlarmDescription": coiAlarmDescription}
)
