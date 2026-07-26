import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def randint():
    # Found rather than spelled out, so organising the bundled scripts into
    # folders does not break the tests for them.
    return load_module(next(discovery.bundled_scripts_dir().rglob("randint.py")))


def values(records):
    assert all(list(record) == ["value"] for record in records)
    return [record["value"] for record in records]


def test_defaults_to_a_hundred_values_from_zero_to_a_hundred(randint):
    got = values(randint.run({}, {}))

    assert len(got) == 100
    assert all(isinstance(value, int) for value in got)
    assert all(0 <= value <= 100 for value in got)


def test_count_is_overridable(randint):
    assert len(randint.run({"count": 7}, {})) == 7


def test_range_is_overridable_and_inclusive(randint):
    got = values(randint.run({"count": 200, "start": 5, "end": 6}, {}))

    assert set(got) == {5, 6}


def test_a_single_value_range(randint):
    assert values(randint.run({"count": 3, "start": 4, "end": 4}, {})) == [4, 4, 4]


def test_negative_range(randint):
    got = values(randint.run({"count": 20, "start": -10, "end": -5}, {}))

    assert all(-10 <= value <= -5 for value in got)


def test_no_values_at_all(randint):
    assert randint.run({"count": 0}, {}) == []


def test_negative_count_is_rejected(randint):
    with pytest.raises(ValueError) as excinfo:
        randint.run({"count": -1}, {})
    assert "cannot be negative" in str(excinfo.value)


def test_backwards_range_is_rejected(randint):
    with pytest.raises(ValueError) as excinfo:
        randint.run({"start": 10, "end": 1}, {})
    assert "is above end" in str(excinfo.value)


def test_non_integer_options_are_rejected(randint):
    for args in ({"count": "lots"}, {"start": 1.5}, {"end": None}):
        with pytest.raises(ArgumentError) as excinfo:
            randint.run(args, {})
        assert "must be a whole number" in str(excinfo.value)


def test_option_given_without_a_value_is_rejected(randint):
    # --count on its own parses to True, which is an int to Python.
    with pytest.raises(ArgumentError) as excinfo:
        randint.run({"count": True}, {})
    assert "--count must be a whole number" in str(excinfo.value)
