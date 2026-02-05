"""Type encoding plugin system for SNMP values.

This module provides plugins that encode Python values to SNMP-compatible types,
handling TEXTUAL-CONVENTIONs and special formatting requirements.
"""

from typing import Any, Dict, Optional
import logging

from app.types import TypeEncoder

logger = logging.getLogger(__name__)

# Registry of type encoders
_type_encoders: Dict[str, TypeEncoder] = {}


def register_type_encoder(type_name: str, encoder: TypeEncoder) -> None:
    """Register an encoder function for a specific SNMP type.

    Args:
        type_name: SNMP type name (e.g., 'DateAndTime', 'DisplayString')
        encoder: Function that encodes Python value to SNMP-compatible format
    """
    _type_encoders[type_name] = encoder
    logger.debug(f"Registered type encoder for {type_name}")


def get_type_encoder(type_name: str) -> Optional[TypeEncoder]:
    """Get the encoder function for a type, if registered.

    Args:
        type_name: SNMP type name

    Returns:
        Encoder function, or None if no encoder registered
    """
    return _type_encoders.get(type_name)


def encode_value(value: Any, type_name: str) -> Any:
    """Encode a value using the registered encoder for its type.

    Args:
        value: The value to encode
        type_name: SNMP type name

    Returns:
        Encoded value, or original value if no encoder registered
    """
    encoder = get_type_encoder(type_name)
    if encoder:
        return encoder(value)
    return value
