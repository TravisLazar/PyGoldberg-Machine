import json
from pathlib import Path

import pytest

from pgm import streams
from pgm.errors import InputError, OutputError


def test_empty_input_is_no_records():
    # Turning that into one empty record is the runner's call, not parsing's.
    assert streams.read_records("") == []
    assert streams.read_records("   \n\n") == []


def test_json_object_becomes_a_record():
    assert streams.read_records('{"a": 1}') == [{"a": 1}]


def test_one_record_per_line():
    text = '{"a": 1}\n{"a": 2}\n'
    assert streams.read_records(text) == [{"a": 1}, {"a": 2}]


def test_json_array_is_flattened():
    assert streams.read_records('[{"a": 1}, {"a": 2}]') == [{"a": 1}, {"a": 2}]


def test_non_json_line_is_rejected():
    with pytest.raises(InputError):
        streams.read_records("just words")


def test_scalar_json_is_rejected():
    for text in ("41", "true", "null", "3.5"):
        with pytest.raises(InputError):
            streams.read_records(text)


def test_json_string_that_is_not_a_path_is_rejected():
    with pytest.raises(InputError):
        streams.read_records('"/definitely/not/here"')


def test_array_of_non_objects_is_rejected():
    with pytest.raises(InputError):
        streams.read_records("[1, 2]")


def test_nested_array_is_rejected():
    with pytest.raises(InputError):
        streams.read_records('[[{"a": 1}]]')


def test_path_input_is_read_from_disk(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text('{"a": 1}\n{"a": 2}\n')

    assert streams.read_records(str(payload)) == [{"a": 1}, {"a": 2}]


def test_quoted_path_input_is_read_from_disk(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text('{"a": 1}')

    assert streams.read_records(json.dumps(str(payload))) == [{"a": 1}]


def test_path_inside_an_array_is_read_from_disk(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text('{"a": 1}')

    assert streams.read_records(json.dumps([str(payload), {"a": 2}])) == [
        {"a": 1},
        {"a": 2},
    ]


def test_path_chains_are_followed(tmp_path):
    leaf = tmp_path / "leaf.json"
    leaf.write_text('{"a": 1}')
    pointer = tmp_path / "pointer.txt"
    pointer.write_text(str(leaf))

    assert streams.read_records(str(pointer)) == [{"a": 1}]


def test_path_loops_are_caught(tmp_path):
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text(str(right))
    right.write_text(str(left))

    with pytest.raises(InputError):
        streams.read_records(str(left))


def test_directories_are_not_treated_as_input(tmp_path):
    with pytest.raises(InputError):
        streams.read_records(str(tmp_path))


def test_dict_renders_as_one_json_line():
    assert streams.render({"b": 2, "a": 1}) == ['{"a": 1, "b": 2}']


def test_list_renders_one_element_per_line():
    assert streams.render([{"a": 1}, {"a": 2}]) == ['{"a": 1}', '{"a": 2}']


def test_list_of_paths_renders_quoted(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text("{}")

    assert streams.render([str(payload)]) == [json.dumps(str(payload))]


def test_list_of_other_types_is_rejected():
    with pytest.raises(OutputError):
        streams.render([1, 2])

    with pytest.raises(OutputError):
        streams.render([["nested"]])


def test_list_of_missing_paths_is_rejected():
    with pytest.raises(OutputError):
        streams.render(["/definitely/not/here"])


def test_string_must_be_an_existing_path(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text("{}")

    assert streams.render(str(payload)) == [str(payload)]

    with pytest.raises(OutputError):
        streams.render("/definitely/not/here")


def test_returned_directory_is_rejected(tmp_path):
    with pytest.raises(OutputError):
        streams.render(str(tmp_path))


def test_multiline_string_is_rejected(tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text("{}")

    with pytest.raises(OutputError):
        streams.render("%s\n%s" % (payload, payload))


def test_none_is_rejected():
    with pytest.raises(OutputError):
        streams.render(None)


def test_set_is_rejected():
    with pytest.raises(OutputError):
        streams.render({"b", "a"})

    with pytest.raises(OutputError):
        streams.render(frozenset(["a"]))


def test_tuple_is_rejected():
    with pytest.raises(OutputError):
        streams.render(({"a": 1},))


def test_unsupported_return_type_is_rejected():
    with pytest.raises(OutputError):
        streams.render(42)


def test_unserializable_return_value_is_rejected():
    with pytest.raises(OutputError):
        streams.render({"when": object()})


def test_nested_set_is_rejected():
    with pytest.raises(OutputError):
        streams.render({"names": {"a", "b"}})


def test_nested_path_object_is_rejected():
    with pytest.raises(OutputError):
        streams.render({"file": Path("/tmp/whatever")})


def test_nan_is_rejected():
    with pytest.raises(OutputError):
        streams.render({"n": float("nan")})
