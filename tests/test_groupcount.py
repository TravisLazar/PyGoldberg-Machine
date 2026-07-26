import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def groupcount():
    return load_module(next(discovery.bundled_scripts_dir().rglob("groupcount.py")))


def records(*values):
    return [{"bucket": value, "extra": "ignored"} for value in values]


def test_counts_each_group(groupcount):
    got = groupcount.run_all({"groupname": "bucket"}, records("a", "b", "a"))

    assert got == [{"bucket": "a", "count": 2}, {"bucket": "b", "count": 1}]


def test_one_group(groupcount):
    got = groupcount.run_all({"groupname": "bucket"}, records("a", "a", "a"))

    assert got == [{"bucket": "a", "count": 3}]


def test_every_record_its_own_group(groupcount):
    got = groupcount.run_all({"groupname": "bucket"}, records("a", "b", "c"))

    assert [group["count"] for group in got] == [1, 1, 1]


def test_groups_keep_the_order_they_were_first_seen(groupcount):
    got = groupcount.run_all({"groupname": "bucket"}, records("c", "a", "b", "a"))

    assert [group["bucket"] for group in got] == ["c", "a", "b"]


def test_numbers_group_as_readily_as_words(groupcount):
    got = groupcount.run_all({"groupname": "bucket"}, records(10, 20, 10))

    assert got == [{"bucket": 10, "count": 2}, {"bucket": 20, "count": 1}]


def test_null_is_a_group_of_its_own(groupcount):
    got = groupcount.run_all({"groupname": "bucket"}, records(None, "a", None))

    assert got == [{"bucket": None, "count": 2}, {"bucket": "a", "count": 1}]


def test_true_and_one_are_not_the_same_group(groupcount):
    got = groupcount.run_all({"groupname": "bucket"}, records(True, 1, True))

    assert got == [{"bucket": True, "count": 2}, {"bucket": 1, "count": 1}]


def test_nothing_in_nothing_out(groupcount):
    assert groupcount.run_all({"groupname": "bucket"}, []) == []


def test_the_group_field_is_required(groupcount):
    with pytest.raises(ArgumentError) as excinfo:
        groupcount.run_all({}, records("a"))
    assert "--groupname is required" in str(excinfo.value)


def test_the_group_field_has_to_be_named(groupcount):
    # --groupname with no value parses to True, which names no field.
    with pytest.raises(ArgumentError) as excinfo:
        groupcount.run_all({"groupname": True}, records("a"))
    assert "--groupname must be text" in str(excinfo.value)


def test_a_record_without_the_field_is_reported(groupcount):
    with pytest.raises(ValueError) as excinfo:
        groupcount.run_all({"groupname": "bucket"}, [{"other": 1, "another": 2}])
    message = str(excinfo.value)
    assert "no 'bucket' to group by" in message
    assert "another, other" in message


def test_an_empty_record_is_reported(groupcount):
    with pytest.raises(ValueError) as excinfo:
        groupcount.run_all({"groupname": "bucket"}, [{}])
    assert "no fields at all" in str(excinfo.value)


def test_a_group_that_cannot_name_itself_is_reported(groupcount):
    for value in ([1, 2], {"a": 1}):
        with pytest.raises(ValueError) as excinfo:
            groupcount.run_all({"groupname": "bucket"}, records(value))
        assert "cannot name a group" in str(excinfo.value)


def test_grouping_by_the_count_field_is_refused(groupcount):
    with pytest.raises(ValueError) as excinfo:
        groupcount.run_all({"groupname": "count"}, [{"count": 1}])
    assert "collides with the field the tally goes in" in str(excinfo.value)
