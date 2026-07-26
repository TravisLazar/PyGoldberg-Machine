import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def sortlist():
    return load_module(next(discovery.bundled_scripts_dir().rglob("sortlist.py")))


def numbers(*values):
    return [{"n": value} for value in values]


def test_sorts_ascending_by_default(sortlist):
    assert sortlist.run_all({"sortkeys": "n"}, numbers(2, 1, 3)) == numbers(1, 2, 3)


def test_ascending_can_be_asked_for(sortlist):
    args = {"sortkeys": "n", "order": "asc"}

    assert sortlist.run_all(args, numbers(2, 1, 3)) == numbers(1, 2, 3)


def test_descending(sortlist):
    args = {"sortkeys": "n", "order": "desc"}

    assert sortlist.run_all(args, numbers(2, 1, 3)) == numbers(3, 2, 1)


def test_the_order_may_be_written_in_any_case(sortlist):
    args = {"sortkeys": "n", "order": "DESC"}

    assert sortlist.run_all(args, numbers(2, 1, 3)) == numbers(3, 2, 1)


def test_text_sorts_as_text(sortlist):
    records = [{"s": "b"}, {"s": "a"}, {"s": "c"}]

    got = sortlist.run_all({"sortkeys": "s"}, records)

    assert [record["s"] for record in got] == ["a", "b", "c"]


def test_a_second_key_settles_what_the_first_one_ties(sortlist):
    records = [
        {"dept": "b", "name": "yolanda"},
        {"dept": "a", "name": "zoe"},
        {"dept": "b", "name": "alan"},
        {"dept": "a", "name": "ada"},
    ]

    got = sortlist.run_all({"sortkeys": "dept,name"}, records)

    assert [(r["dept"], r["name"]) for r in got] == [
        ("a", "ada"),
        ("a", "zoe"),
        ("b", "alan"),
        ("b", "yolanda"),
    ]


def test_descending_turns_every_key_around_together(sortlist):
    records = [
        {"dept": "a", "name": "ada"},
        {"dept": "b", "name": "alan"},
        {"dept": "a", "name": "zoe"},
    ]

    got = sortlist.run_all({"sortkeys": "dept,name", "order": "desc"}, records)

    assert [(r["dept"], r["name"]) for r in got] == [
        ("b", "alan"),
        ("a", "zoe"),
        ("a", "ada"),
    ]


def test_records_that_tie_on_everything_keep_the_order_they_arrived_in(sortlist):
    records = [{"n": 1, "id": "first"}, {"n": 1, "id": "second"}, {"n": 0, "id": "third"}]

    got = sortlist.run_all({"sortkeys": "n"}, records)

    assert [record["id"] for record in got] == ["third", "first", "second"]


def test_ties_keep_their_order_going_down_as_well(sortlist):
    records = [{"n": 1, "id": "first"}, {"n": 1, "id": "second"}, {"n": 2, "id": "third"}]

    got = sortlist.run_all({"sortkeys": "n", "order": "desc"}, records)

    assert [record["id"] for record in got] == ["third", "first", "second"]


def test_space_around_the_commas_is_ignored(sortlist):
    records = [{"a": 2, "b": 1}, {"a": 1, "b": 2}]

    got = sortlist.run_all({"sortkeys": " a , b "}, records)

    assert [record["a"] for record in got] == [1, 2]


def test_nothing_in_nothing_out(sortlist):
    assert sortlist.run_all({"sortkeys": "n"}, []) == []


def test_one_record_is_already_sorted(sortlist):
    assert sortlist.run_all({"sortkeys": "n"}, numbers(5)) == numbers(5)


def test_the_sort_keys_are_required(sortlist):
    with pytest.raises(ArgumentError) as excinfo:
        sortlist.run_all({}, numbers(1))
    assert "--sortkeys is required" in str(excinfo.value)


def test_the_sort_keys_have_to_be_named(sortlist):
    # --sortkeys with no value parses to True, which names no field.
    with pytest.raises(ArgumentError) as excinfo:
        sortlist.run_all({"sortkeys": True}, numbers(1))
    assert "--sortkeys must be text" in str(excinfo.value)


def test_an_empty_key_is_refused(sortlist):
    for given in ("", "n,", ",n", "a,,b", " "):
        with pytest.raises(ValueError) as excinfo:
            sortlist.run_all({"sortkeys": given}, numbers(1))
        assert "empty key" in str(excinfo.value)


def test_an_order_that_is_neither_is_refused(sortlist):
    with pytest.raises(ValueError) as excinfo:
        sortlist.run_all({"sortkeys": "n", "order": "sideways"}, numbers(1))
    assert "--order must be asc or desc, got 'sideways'" in str(excinfo.value)


def test_a_record_without_the_key_is_reported(sortlist):
    records = [{"n": 1}, {"other": 2, "another": 3}]

    with pytest.raises(ValueError) as excinfo:
        sortlist.run_all({"sortkeys": "n"}, records)
    message = str(excinfo.value)
    assert "no 'n' to sort by" in message
    assert "another, other" in message


def test_a_second_key_is_checked_too(sortlist):
    records = [{"a": 1, "b": 1}, {"a": 2}]

    with pytest.raises(ValueError) as excinfo:
        sortlist.run_all({"sortkeys": "a,b"}, records)
    assert "no 'b' to sort by" in str(excinfo.value)


def test_a_key_holding_numbers_and_text_is_refused(sortlist):
    with pytest.raises(ValueError) as excinfo:
        sortlist.run_all({"sortkeys": "n"}, numbers(1, "two"))
    assert "'n' holds both numbers and text" in str(excinfo.value)


def test_a_null_cannot_be_put_in_order(sortlist):
    with pytest.raises(ValueError) as excinfo:
        sortlist.run_all({"sortkeys": "n"}, numbers(1, None))
    assert "'n' is null in a record" in str(excinfo.value)


def test_a_list_or_a_dict_cannot_be_put_in_order(sortlist):
    for value in ([1], {"a": 1}):
        with pytest.raises(ValueError) as excinfo:
            sortlist.run_all({"sortkeys": "n"}, numbers(value))
        assert "cannot be put in order" in str(excinfo.value)


def test_whole_and_fractional_numbers_sort_together(sortlist):
    got = sortlist.run_all({"sortkeys": "n"}, numbers(2, 1.5, 3))

    assert [record["n"] for record in got] == [1.5, 2, 3]
