"""MIB metadata and OID mappings for sysORTable population."""

# Map of MIB names to their root or module OIDs and descriptions
# These represent the MIBs/modules that this agent implements
MIB_METADATA = {
    "SNMPv2-MIB": {
        "oid": [1, 3, 6, 1, 2, 1, 11, 2, 1],  # snmpMIB compliance
        "description": "The MIB module for SNMPv2 entities",
    },
    "IF-MIB": {
        "oid": [1, 3, 6, 1, 2, 1, 2],  # interfaces subtree root
        "description": "The MIB module for managing network interfaces",
    },
    "HOST-RESOURCES-MIB": {
        "oid": [1, 3, 6, 1, 2, 1, 25],  # host subtree root
        "description": "The MIB module for Host Resources",
    },
    "HOST-RESOURCES-TYPES": {
        "oid": [1, 3, 6, 1, 2, 1, 25, 3, 1],  # hrDeviceTypes
        "description": "Host Resources types and textual conventions",
    },
    "CISCO-ALARM-MIB": {
        "oid": [1, 3, 6, 1, 4, 1, 9, 9, 46],  # Cisco alarm management
        "description": "Cisco Alarm MIB for alarm management",
    },
}


def get_sysor_table_rows(mib_names: list[str]) -> list[dict[str, object]]:
    """Generate sysORTable rows based on the MIBs being served.

    Args:
        mib_names: List of MIB names (e.g., ['SNMPv2-MIB', 'IF-MIB', ...])

    Returns:
        List of sysORTable rows with index, OID, description, and uptime
    """
    rows = []
    index = 1

    for mib_name in mib_names:
        if mib_name in MIB_METADATA:
            metadata = MIB_METADATA[mib_name]
            rows.append(
                {
                    "sysORIndex": index,
                    "sysORID": metadata["oid"],
                    "sysORDescr": metadata["description"],
                    "sysORUpTime": index * 10,  # Incrementing TimeTicks (10, 20, 30...)
                }
            )
            index += 1

    return rows
