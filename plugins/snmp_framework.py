"""SNMP Framework MIB default value plugin.

Handles SNMPv3 and SNMP Framework MIB objects that require special consideration:
- snmpEngineID: Should be stable for a given agent instance
- Other framework-related objects
"""

import hashlib
import os
import socket
from typing import Any, Optional
from app.default_value_plugins import register_plugin
from app.types import TypeInfo


def _generate_stable_engine_id() -> bytes:
    """Generate a stable SNMP Engine ID for this agent instance.
    
    The snmpEngineID is used in SNMPv3 security associations and should be stable
    for a given agent instance. It should not change between restarts or requests.
    
    Uses RFC 3414 format:
    - Byte 0-3: 0x80 (private enterprises identifier)
    - Byte 4-7: Enterprise number (using 99999 like sysObjectID)
    - Byte 8+: Implementation-specific suffix (hostname + hash for stability)
    
    This generates a pseudo-random but stable ID based on the system hostname
    and a fixed salt. The same hostname will always produce the same ID.
    """
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "python-snmp-agent"
    
    # RFC 3414 format prefix: 0x80 (private) + enterprise number (99999 = 0x0001869F)
    # Then add implementation-specific suffix for stability
    prefix = b'\x80\x00\x01\x86\x9f'
    
    # Create stable suffix from hostname using SHA256
    # Using a fixed salt ensures the same hostname produces the same suffix
    salt = b'snmp-agent-engine-id-v1'
    suffix_hash = hashlib.sha256(hostname.encode() + salt).digest()
    
    # Take first 11 bytes of hash to keep the full ID under typical length
    # Total: 5 (prefix) + 11 (suffix) = 16 bytes, which is reasonable
    engine_id = prefix + suffix_hash[:11]
    
    return engine_id


# Cache the engine ID so it remains stable within the process
_CACHED_ENGINE_ID: Optional[bytes] = None


def _get_stable_engine_id() -> bytes:
    """Get the cached or newly generated stable engine ID."""
    global _CACHED_ENGINE_ID
    if _CACHED_ENGINE_ID is None:
        _CACHED_ENGINE_ID = _generate_stable_engine_id()
    return _CACHED_ENGINE_ID


@register_plugin("snmp_framework")
def get_default_value(type_info: TypeInfo, symbol_name: str) -> Any:
    """Provide default values for SNMP Framework MIB objects."""
    
    # snmpEngineID must be stable across agent restarts
    if symbol_name == "snmpEngineID":
        # Return as list of byte values (0-255) as expected by SNMP
        engine_id = _get_stable_engine_id()
        return list(engine_id)
    
    # Could add other SNMP Framework defaults here
    # For now, only handle snmpEngineID specifically
    
    return None
