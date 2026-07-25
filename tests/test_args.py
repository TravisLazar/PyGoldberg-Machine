import pytest

from pgm.args import parse_script_args, split_argv
from pgm.errors import ArgumentError


def split(*argv):
    """Return (script, leftover tokens) for a command line."""
    _, script, extra = split_argv(list(argv))
    return script, extra


def args(*argv):
    """Parse a whole command line down to the script's args dict."""
    _, _, extra = split_argv(list(argv))
    return parse_script_args(extra)


def test_script_name_alone():
    assert split("hello") == ("hello", [])


def test_no_script_name():
    assert split() == (None, [])
    assert split("--dry") == (None, ["--dry"])


def test_option_with_no_value_is_true():
    assert args("--dry", "hello") == {"dry": True}


def test_option_with_a_value():
    assert args("--verbosity=3", "hello") == {"verbosity": 3}
    assert args("--logpath=path/to/file", "hello") == {
        "logpath": "path/to/file"
    }


def test_position_does_not_matter():
    expected = {"dry": True, "logpath": "out.txt", "verbosity": 3}

    assert args("--dry", "--logpath=out.txt", "--verbosity=3", "hello") == expected
    assert args("hello", "--dry", "--logpath=out.txt", "--verbosity=3") == expected
    assert args("--dry", "hello", "--logpath=out.txt", "--verbosity=3") == expected
    assert args("--logpath=out.txt", "--dry", "hello", "--verbosity=3") == expected


def test_script_name_is_found_wherever_it_sits():
    assert split("--dry", "hello")[0] == "hello"
    assert split("hello", "--dry")[0] == "hello"
    assert split("--dry", "hello", "--verbosity=3")[0] == "hello"


def test_pgm_options_are_never_the_scripts():
    pgm_options, script, extra = split_argv(["--traceback", "hello", "--dry"])

    assert pgm_options == ["--traceback"]
    assert script == "hello"
    assert parse_script_args(extra) == {"dry": True}


def test_pgm_options_do_not_claim_the_script_name():
    assert split("--traceback", "hello") == ("hello", [])
    assert split("--where", "hello") == ("hello", [])


def test_dashes_in_names_become_underscores():
    assert args("--log-path=out.txt", "hello") == {"log_path": "out.txt"}


def test_json_values_are_decoded():
    assert args("--n=3", "--pi=1.5", "--on=true", "--off=false", "s") == {
        "n": 3,
        "pi": 1.5,
        "on": True,
        "off": False,
    }


def test_lists_and_objects_are_decoded():
    assert args('--tags=["a", "b"]', "s") == {"tags": ["a", "b"]}
    assert args('--filter={"a": 1}', "s") == {"filter": {"a": 1}}


def test_non_json_values_stay_strings():
    assert args("--name=Travis", "s") == {"name": "Travis"}
    assert args("--logpath=path/to/file", "s") == {"logpath": "path/to/file"}
    assert args("--empty=", "s") == {"empty": ""}


def test_json_lookalikes_that_are_not_json_stay_strings():
    assert args("--n=NaN", "s") == {"n": "NaN"}
    assert args("--n=Infinity", "s") == {"n": "Infinity"}


def test_negative_numbers_are_values_like_any_other():
    assert args("--offset=-3", "s") == {"offset": -3}


def test_short_options_work_the_same_way():
    assert args("-v", "s") == {"v": True}
    assert args("-n=3", "s") == {"n": 3}


def test_separate_value_is_rejected_with_the_fix():
    with pytest.raises(ArgumentError) as excinfo:
        args("--logpath", "out.txt", "hello")
    assert "did you mean --logpath=out.txt?" in str(excinfo.value)


def test_separate_value_after_the_script_name_is_rejected():
    with pytest.raises(ArgumentError) as excinfo:
        args("hello", "--logpath", "out.txt")
    assert "did you mean --logpath=out.txt?" in str(excinfo.value)


def test_two_script_names_are_rejected():
    with pytest.raises(ArgumentError) as excinfo:
        args("hello", "extra")
    assert "one script at a time" in str(excinfo.value)


def test_negative_number_written_with_a_space_is_rejected():
    with pytest.raises(ArgumentError) as excinfo:
        args("--offset", "-3", "s")
    assert "'-3' is not an option name" in str(excinfo.value)


def test_repeated_option_is_rejected():
    with pytest.raises(ArgumentError) as excinfo:
        args("--tag=a", "--tag=b", "hello")
    assert "more than once" in str(excinfo.value)


def test_repeated_option_is_rejected_across_spellings():
    with pytest.raises(ArgumentError):
        args("--log-path=a", "--log_path=b", "hello")


def test_pgm_option_given_a_value_is_rejected():
    with pytest.raises(ArgumentError) as excinfo:
        args("--traceback=true", "hello")
    assert "pgm's own option" in str(excinfo.value)


def test_dashes_without_a_name_are_rejected():
    for token in ("-", "--", "--="):
        with pytest.raises(ArgumentError):
            args(token, "hello")


def test_bare_word_reaching_the_parser_is_rejected():
    with pytest.raises(ArgumentError) as excinfo:
        parse_script_args(["stray"])
    assert "unexpected argument 'stray'" in str(excinfo.value)


def test_no_tokens_means_no_args():
    assert parse_script_args([]) == {}
