"""
Tests for the plugins module.
"""
from typing import Any

from plugins.basic_types import get_default_value as basic_get_default_value, _get_first_enum_value
from plugins.date_and_time import _format_date_and_time
from plugins.snmp_framework import get_default_value as framework_get_default_value
from plugins.type_encoders import register_type_encoder, get_type_encoder, encode_value

class TestBasicTypesPlugin:
    """Test the basic_types plugin."""

    def test_get_first_enum_value_dict_format(self) -> None:
        """Test _get_first_enum_value with dict format."""
        enums = {"up": 1, "down": 2, "testing": 3}
        result = _get_first_enum_value(enums)
        assert result == 1  # Should return lowest value

    def test_get_first_enum_value_list_format(self) -> None:
        """Test _get_first_enum_value with list format."""
        enums = [{"value": 2, "name": "down"}, {"value": 1, "name": "up"}]
        result = _get_first_enum_value(enums)
        assert result == 2  # Should return first item

    def test_get_first_enum_value_empty(self) -> None:
        """Test _get_first_enum_value with empty enums."""
        assert _get_first_enum_value(None) is None
        assert _get_first_enum_value([]) is None
        assert _get_first_enum_value({}) is None

    def test_sysdescr_default(self) -> None:
        """Test sysDescr gets proper default."""
        result = basic_get_default_value({}, "sysDescr")
        assert result == "Simple Python SNMP Agent"

    def test_sysobjectid_default(self) -> None:
        """Test sysObjectID gets proper default."""
        result = basic_get_default_value({}, "sysObjectID")
        assert result == [1, 3, 6, 1, 4, 1, 99999]

    def test_syscontact_default(self) -> None:
        """Test sysContact gets proper default."""
        result = basic_get_default_value({}, "sysContact")
        assert result == "Admin <admin@example.com>"

    def test_sysname_default(self) -> None:
        """Test sysName gets proper default."""
        result = basic_get_default_value({}, "sysName")
        assert result == "snmp-agent"

    def test_syslocation_default(self) -> None:
        """Test sysLocation gets proper default."""
        result = basic_get_default_value({}, "sysLocation")
        assert result == "Server Room"

    def test_sysuptime_default(self) -> None:
        """Test sysUpTime gets proper default."""
        result = basic_get_default_value({}, "sysUpTime")
        assert result == 0

    def test_sysservices_default(self) -> None:
        """Test sysServices gets proper default."""
        result = basic_get_default_value({}, "sysServices")
        assert result == 72

    def test_mac_address_fields(self) -> None:
        """Test MAC address fields get proper null MAC."""
        mac_fields = ["ifPhysAddress", "ipNetMediaPhysAddress", "atPhysAddress"]
        for field in mac_fields:
            result = basic_get_default_value({}, field)
            assert result == [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    def test_physaddress_macaddress_fields(self) -> None:
        """Test fields containing PhysAddress or MacAddress get null MAC."""
        result = basic_get_default_value({}, "somePhysAddress")
        assert result == [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

        result = basic_get_default_value({}, "someMacAddress")
        assert result == [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    def test_octetstring_default(self) -> None:
        """Test OctetString types get 'unset' default."""
        type_infos = [
            {"base_type": "OctetString"},
            {"base_type": "DisplayString"},
            {"base_type": "SnmpAdminString"},
            {"base_type": "OCTET STRING"}
        ]
        for type_info in type_infos:
            result = basic_get_default_value(type_info, "someString")
            assert result == "unset"

    def test_octetstring_mac_address_override(self) -> None:
        """Test OctetString with MAC address names get null MAC."""
        type_info = {"base_type": "OctetString"}
        result = basic_get_default_value(type_info, "ifPhysAddress")
        assert result == [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    def test_objectidentifier_default(self) -> None:
        """Test ObjectIdentifier types get [0, 0] default."""
        type_infos = [
            {"base_type": "ObjectIdentifier"},
            {"base_type": "AutonomousType"},
            {"base_type": "OBJECT IDENTIFIER"}
        ]
        for type_info in type_infos:
            result = basic_get_default_value(type_info, "someOid")
            assert result == [0, 0]

    def test_integer_types_with_enums(self) -> None:
        """Test integer types with enums return first enum value."""
        type_info = {
            "base_type": "Integer32",
            "enums": {"up": 1, "down": 2, "testing": 3}
        }
        result = basic_get_default_value(type_info, "someInt")
        assert result == 1  # First (lowest) enum value

    def test_integer_types_without_enums(self) -> None:
        """Test integer types without enums return 0."""
        type_infos = [
            {"base_type": "Integer32"},
            {"base_type": "Integer"},
            {"base_type": "Gauge32"},
            {"base_type": "Unsigned32"},
            {"base_type": "INTEGER"}
        ]
        for type_info in type_infos:
            result = basic_get_default_value(type_info, "someInt")
            assert result == 0

    def test_counter_types(self) -> None:
        """Test counter types return 0."""
        type_infos = [
            {"base_type": "Counter32"},
            {"base_type": "Counter64"}
        ]
        for type_info in type_infos:
            result = basic_get_default_value(type_info, "someCounter")
            assert result == 0

    def test_ipaddress_default(self) -> None:
        """Test IpAddress type gets [0, 0, 0, 0] default."""
        result = basic_get_default_value({"base_type": "IpAddress"}, "someIp")
        assert result == [0, 0, 0, 0]

    def test_timeticks_default(self) -> None:
        """Test TimeTicks type gets 0 default."""
        result = basic_get_default_value({"base_type": "TimeTicks"}, "someTime")
        assert result == 0

    def test_bits_default(self) -> None:
        """Test Bits type gets empty list default."""
        result = basic_get_default_value({"base_type": "Bits"}, "someBits")
        assert result == []

    def test_opaque_default(self) -> None:
        """Test Opaque type gets empty list default."""
        result = basic_get_default_value({"base_type": "Opaque"}, "someOpaque")
        assert result == []

    def test_physaddress_default(self) -> None:
        """Test PhysAddress type gets null MAC default."""
        result = basic_get_default_value({"base_type": "PhysAddress"}, "somePhys")
        assert result == [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    def test_macaddress_default(self) -> None:
        """Test MacAddress type gets null MAC default."""
        result = basic_get_default_value({"base_type": "MacAddress"}, "someMac")
        assert result == [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    def test_dateandtime_default(self) -> None:
        """Test DateAndTime type gets proper default."""
        result = basic_get_default_value({"base_type": "DateAndTime"}, "someDate")
        assert result == "2026-01-01,00:00:00.0"

    def test_truthvalue_default(self) -> None:
        """Test TruthValue type gets 1 (true) default."""
        result = basic_get_default_value({"base_type": "TruthValue"}, "someTruth")
        assert result == 1

    def test_rowstatus_default(self) -> None:
        """Test RowStatus type gets 1 (active) default."""
        result = basic_get_default_value({"base_type": "RowStatus"}, "someRow")
        assert result == 1

    def test_storagetype_default(self) -> None:
        """Test StorageType type gets 3 (volatile) default."""
        result = basic_get_default_value({"base_type": "StorageType"}, "someStorage")
        assert result == 3

    def test_unknown_type(self) -> None:
        """Test unknown types return None."""
        result = basic_get_default_value({"base_type": "UnknownType"}, "someUnknown")
        assert result is None


class TestDateAndTimePlugin:
    """Test the date_and_time plugin."""

    def test_format_date_and_time_current_time(self) -> None:
        """Test _format_date_and_time with None/unset values returns current time."""
        result = _format_date_and_time(None)
        assert isinstance(result, bytes)
        assert len(result) == 11  # 11 octets for RFC compliant format

        result = _format_date_and_time("unset")
        assert isinstance(result, bytes)
        assert len(result) == 11

        result = _format_date_and_time("")
        assert isinstance(result, bytes)
        assert len(result) == 11

        result = _format_date_and_time("unknown")
        assert isinstance(result, bytes)
        assert len(result) == 11

    def test_format_date_and_time_bytes_passthrough(self) -> None:
        """Test _format_date_and_time passes through valid bytes."""
        test_bytes = b'\x07\xe6\x01\x01\x00\x00\x00\x00\x00\x00\x00'  # 2022-01-01 00:00:00.0 +00:00
        result = _format_date_and_time(test_bytes)
        assert result == test_bytes

    def test_format_date_and_time_short_bytes(self) -> None:
        """Test _format_date_and_time with short bytes returns current time."""
        short_bytes = b'\x07\xe6\x01\x01'  # Only 4 bytes
        result = _format_date_and_time(short_bytes)
        assert isinstance(result, bytes)
        assert len(result) == 11  # Should format as current time

    def test_format_date_and_time_string_parsing(self) -> None:
        """Test _format_date_and_time parses datetime strings."""
        # Test ISO format with comma - use current year (2026 = 0x07ea)
        result = _format_date_and_time("2026-01-01,12:30:45.5")
        assert isinstance(result, bytes)
        assert len(result) == 11

        # Should contain year 2026 (0x07ea in big-endian)
        assert result[0:2] == b'\x07\xea'


class TestSNMPFrameworkPlugin:
    """Test the snmp_framework plugin."""

    def test_snmpengineid_default(self) -> None:
        """Test snmpEngineID gets a stable default."""
        result = framework_get_default_value({}, "snmpEngineID")
        assert isinstance(result, list)
        assert len(result) > 5  # Should have prefix + suffix
        assert result[:5] == [128, 0, 1, 134, 159]  # RFC 3414 format prefix

    def test_snmpengineid_stable(self, mocker: Any) -> None:
        """Test snmpEngineID is stable for the same hostname."""
        mock_hostname = mocker.patch('plugins.snmp_framework.socket.gethostname')
        mock_hostname.return_value = "test-host"

        result1 = framework_get_default_value({}, "snmpEngineID")
        result2 = framework_get_default_value({}, "snmpEngineID")

        assert result1 == result2  # Should be identical due to caching

    def test_snmpengineid_caching_behavior(self, mocker: Any) -> None:
        """Test that snmpEngineID caching works correctly."""
        mock_hostname = mocker.patch('plugins.snmp_framework.socket.gethostname')
        mocker.patch('plugins.snmp_framework._CACHED_ENGINE_ID', None)
        mock_hostname.return_value = "test-host"
        
        # First call should generate and cache
        result1 = framework_get_default_value({}, "snmpEngineID")
        
        # Second call should return cached value
        result2 = framework_get_default_value({}, "snmpEngineID")
        
        assert result1 == result2  # Should be identical due to caching
        assert isinstance(result1, list)
        assert len(result1) == 16  # 5 prefix + 11 hash bytes

    def test_unknown_symbol(self) -> None:
        """Test unknown symbols return None."""
        result = framework_get_default_value({}, "unknownSymbol")
        assert result is None


class TestTypeEncodersPlugin:
    """Test the type_encoders plugin."""

    def test_register_and_get_encoder(self) -> None:
        """Test registering and retrieving type encoders."""
        def test_encoder(value: Any) -> Any:
            return f"encoded_{value}"

        register_type_encoder("TestType", test_encoder)
        encoder = get_type_encoder("TestType")
        assert encoder == test_encoder

    def test_get_nonexistent_encoder(self) -> None:
        """Test getting encoder for unregistered type returns None."""
        encoder = get_type_encoder("NonExistentType")
        assert encoder is None

    def test_encode_value_with_encoder(self) -> None:
        """Test encode_value uses registered encoder."""
        def test_encoder(value: Any) -> Any:
            return f"encoded_{value}"

        register_type_encoder("TestType2", test_encoder)
        result = encode_value("test", "TestType2")
        assert result == "encoded_test"

    def test_encode_value_without_encoder(self) -> None:
        """Test encode_value returns original value when no encoder registered."""
        result = encode_value("test", "UnregisteredType")
        assert result == "test"