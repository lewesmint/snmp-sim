from app.snmp_agent import SNMPAgent


def test_decode_value_passthrough() -> None:
    agent = SNMPAgent()
    assert agent._decode_value(123) == 123
    assert agent._decode_value("abc") == "abc"


def test_decode_value_hex() -> None:
    agent = SNMPAgent()
    v = {"value": "\\xAA\\xBB", "encoding": "hex"}
    decoded = agent._decode_value(v)
    assert isinstance(decoded, (bytes, bytearray))
    assert decoded == b"\xAA\xBB"


def test_decode_value_unknown_encoding() -> None:
    agent = SNMPAgent()
    v = {"value": "zzz", "encoding": "base64"}
    # unknown encoding should return raw encoded value
    assert agent._decode_value(v) == "zzz"
