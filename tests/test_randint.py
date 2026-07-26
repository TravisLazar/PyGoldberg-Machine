import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def randint():
    # Found rather than spelled out, so organising the bundled scripts into
    # folders does not break the tests for them.
    return load_module(next(discovery.bundled_scripts_dir().rglob("randint.py")))


def values(records, key="value"):
    assert all(key in record for record in records)
    return [record[key] for record in records]


def test_defaults_to_a_hundred_values_from_zero_to_a_hundred(randint):
    got = values(randint.run_all({}, []))

    assert len(got) == 100
    assert all(isinstance(value, int) for value in got)
    assert all(0 <= value <= 100 for value in got)


def test_count_is_overridable(randint):
    assert len(randint.run_all({"count": 7}, [])) == 7


def test_range_is_overridable_and_inclusive(randint):
    got = values(randint.run_all({"count": 200, "start": 5, "end": 6}, []))

    assert set(got) == {5, 6}


def test_a_single_value_range(randint):
    assert values(randint.run_all({"count": 3, "start": 4, "end": 4}, [])) == [4, 4, 4]


def test_negative_range(randint):
    got = values(randint.run_all({"count": 20, "start": -10, "end": -5}, []))

    assert all(-10 <= value <= -5 for value in got)


def test_no_values_at_all(randint):
    assert randint.run_all({"count": 0}, []) == []


def test_the_field_can_be_named(randint):
    got = randint.run_all({"count": 3, "key": "roll", "start": 1, "end": 1}, [])

    assert got == [{"roll": 1}, {"roll": 1}, {"roll": 1}]


def test_records_that_arrive_get_a_field_filled_in(randint):
    records = [{"name": "a"}, {"name": "b"}]

    got = randint.run_all({"start": 5, "end": 5}, records)

    assert got == [{"name": "a", "value": 5}, {"name": "b", "value": 5}]


def test_two_of_them_make_two_columns(randint):
    first = randint.run_all({"count": 3, "start": 1, "end": 1}, [])
    second = randint.run_all({"key": "other", "start": 2, "end": 2}, first)

    assert second == [{"value": 1, "other": 2}] * 3


def test_filling_in_leaves_the_records_it_was_given_alone(randint):
    records = [{"name": "a"}]

    randint.run_all({"start": 1, "end": 1}, records)

    assert records == [{"name": "a"}]


def test_a_count_that_agrees_is_no_trouble(randint):
    records = [{"name": "a"}, {"name": "b"}]

    got = randint.run_all({"count": 2, "start": 1, "end": 1}, records)

    assert values(got) == [1, 1]


def test_a_count_that_disagrees_is_an_invalid_shape(randint):
    records = [{"name": "a"}, {"name": "b"}]

    with pytest.raises(ValueError) as excinfo:
        randint.run_all({"count": 5}, records)
    message = str(excinfo.value)
    assert "invalid shape" in message
    assert "--count=5 but 2 records arrived" in message


def test_a_field_that_is_already_there_is_not_written_over(randint):
    with pytest.raises(ValueError) as excinfo:
        randint.run_all({}, [{"value": 1}])
    assert "already has 'value' in it" in str(excinfo.value)
    assert "--key" in str(excinfo.value)


def test_negative_count_is_rejected(randint):
    with pytest.raises(ValueError) as excinfo:
        randint.run_all({"count": -1}, [])
    assert "cannot be negative" in str(excinfo.value)


def test_backwards_range_is_rejected(randint):
    with pytest.raises(ValueError) as excinfo:
        randint.run_all({"start": 10, "end": 1}, [])
    assert "is above end" in str(excinfo.value)


def test_non_integer_options_are_rejected(randint):
    for args in ({"count": "lots"}, {"start": 1.5}, {"end": None}):
        with pytest.raises(ArgumentError) as excinfo:
            randint.run_all(args, [])
        assert "must be a whole number" in str(excinfo.value)


def test_option_given_without_a_value_is_rejected(randint):
    # --count on its own parses to True, which is an int to Python.
    with pytest.raises(ArgumentError) as excinfo:
        randint.run_all({"count": True}, [])
    assert "--count must be a whole number" in str(excinfo.value)


def test_the_field_name_has_to_be_a_name(randint):
    with pytest.raises(ArgumentError) as excinfo:
        randint.run_all({"key": True, "count": 1}, [])
    assert "--key must be text" in str(excinfo.value)
