from aiowamp.serializers import json


def test_json_encoder():
    e = json.JSONEncoder()
    assert e.encode(bytes.fromhex("10e3ff9053075c526f5fc06d4fe37cdb")) == '"\\u0000EOP/kFMHXFJvX8BtT+N82w=="'


def test_json_decoder():
    d = json.JSONDecoder()
    assert d.decode('"\\u0000EOP/kFMHXFJvX8BtT+N82w=="') == bytes.fromhex("10e3ff9053075c526f5fc06d4fe37cdb")

    obj = d.decode('{"a": ["hello world", 5, "\\u0000EOP/kFMHXFJvX8BtT+N82w=="]}')
    assert obj == {"a": ["hello world", 5, bytes.fromhex("10e3ff9053075c526f5fc06d4fe37cdb")]}
