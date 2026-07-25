import pytest

from pgm import get_float, get_int, get_str, log
from pgm.errors import ArgumentError
from pgm.helpers import set_script_name


@pytest.fixture(autouse=True)
def unnamed():
    """Most tests want log() plain; the runner is what names a script."""
    set_script_name(None)
    yield
    set_script_name(None)


def test_get_int_reads_a_whole_number():
    assert get_int({"count": 7}, "count") == 7
    assert get_int({"count": -7}, "count") == -7


def test_get_int_falls_back_to_the_default():
    assert get_int({}, "count", 100) == 100


def test_get_int_rejects_everything_else():
    for value in (1.5, "lots", None, [1], {"a": 1}):
        with pytest.raises(ArgumentError) as excinfo:
            get_int({"count": value}, "count", 100)
        assert "--count must be a whole number" in str(excinfo.value)


def test_get_int_rejects_a_bare_option():
    # --count with no value parses to True, and True is an int to Python.
    with pytest.raises(ArgumentError) as excinfo:
        get_int({"count": True}, "count", 100)
    assert "--count must be a whole number, got True" in str(excinfo.value)


def test_get_float_reads_a_number():
    assert get_float({"rate": 1.5}, "rate") == 1.5
    assert get_float({"rate": -0.25}, "rate") == -0.25


def test_get_float_widens_a_whole_number():
    value = get_float({"rate": 2}, "rate")

    assert value == 2.0
    assert isinstance(value, float)


def test_get_float_rejects_everything_else():
    for value in ("fast", True, None, [1]):
        with pytest.raises(ArgumentError) as excinfo:
            get_float({"rate": value}, "rate", 1.0)
        assert "--rate must be a number" in str(excinfo.value)


def test_get_str_reads_text():
    assert get_str({"logpath": "out.txt"}, "logpath") == "out.txt"
    assert get_str({"logpath": ""}, "logpath") == ""


def test_get_str_rejects_everything_else():
    for value in (42, 1.5, True, None, ["a"]):
        with pytest.raises(ArgumentError) as excinfo:
            get_str({"logpath": value}, "logpath", "out.txt")
        assert "--logpath must be text" in str(excinfo.value)


def test_get_str_spells_out_numbers_when_asked():
    assert get_str({"port": 8080}, "port", cast_numbers=True) == "8080"
    assert get_str({"rate": 1.5}, "rate", cast_numbers=True) == "1.5"
    assert get_str({"n": -3}, "n", cast_numbers=True) == "-3"


def test_casting_numbers_leaves_text_alone():
    assert get_str({"logpath": "out.txt"}, "logpath", cast_numbers=True) == "out.txt"


def test_casting_numbers_is_off_by_default():
    with pytest.raises(ArgumentError) as excinfo:
        get_str({"port": 8080}, "port", "")
    assert "--port must be text, got 8080" in str(excinfo.value)


def test_casting_numbers_still_refuses_a_bare_option():
    # --port with no value is a forgotten value, not the text "True".
    with pytest.raises(ArgumentError) as excinfo:
        get_str({"port": True}, "port", "", cast_numbers=True)
    assert "--port must be text or a number, got True" in str(excinfo.value)


def test_casting_numbers_refuses_everything_that_is_not_one():
    for value in (None, ["8080"], {"port": 1}):
        with pytest.raises(ArgumentError) as excinfo:
            get_str({"port": value}, "port", "", cast_numbers=True)
        assert "--port must be text or a number" in str(excinfo.value)


def test_casting_numbers_does_not_reach_the_default():
    # Defaults belong to the script, so they are handed back as they are.
    assert get_str({}, "port", 8080, cast_numbers=True) == 8080


def test_a_value_matching_the_default_is_still_a_value():
    assert get_str({"port": 8080}, "port", 8080, cast_numbers=True) == "8080"


def test_a_missing_option_with_no_default_is_required():
    for reader in (get_int, get_float, get_str):
        with pytest.raises(ArgumentError) as excinfo:
            reader({}, "logpath")
        assert "--logpath is required" in str(excinfo.value)


def test_the_option_is_named_as_it_was_typed():
    with pytest.raises(ArgumentError) as excinfo:
        get_int({"log_path": "x"}, "log_path", 1)
    assert "--log-path must be" in str(excinfo.value)


def test_a_default_is_the_scripts_own_business():
    # Not the user's mistake to report, so it is handed back untouched.
    assert get_int({}, "count", None) is None
    assert get_str({}, "logpath", None) is None
    assert get_float({}, "rate", None) is None


def test_log_writes_a_line_to_stderr(capsys):
    log("hello")

    captured = capsys.readouterr()
    assert captured.err == "hello\n"
    assert captured.out == ""


def test_log_joins_and_stringifies_its_parts(capsys):
    log("read", 3, "rows from", None)

    assert capsys.readouterr().err == "read 3 rows from None\n"


def test_log_with_nothing_to_say(capsys):
    log()

    assert capsys.readouterr().err == "\n"


def test_log_names_the_script_that_is_speaking(capsys):
    set_script_name("randint")
    log("counting")

    assert capsys.readouterr().err == "randint: counting\n"
