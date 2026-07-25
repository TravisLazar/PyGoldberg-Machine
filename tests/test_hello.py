import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def hello():
    return load_module(discovery.bundled_scripts_dir() / "hello.py")


def test_greets_both_halves_of_a_name(hello):
    got = hello.run({}, {"firstname": "Ada", "lastname": "Lovelace"})

    assert got == {"name": "Ada Lovelace", "greeting": "Hello, Ada Lovelace!"}


def test_either_half_on_its_own(hello):
    assert hello.run({}, {"firstname": "Ada"})["name"] == "Ada"
    assert hello.run({}, {"lastname": "Lovelace"})["name"] == "Lovelace"


def test_an_empty_record_still_gets_a_greeting(hello):
    got = hello.run({}, {})

    assert got == {"name": "Anonymous", "greeting": "Hello, Anonymous!"}


def test_empty_names_are_the_same_as_none_at_all(hello):
    assert hello.run({}, {"firstname": "", "lastname": ""})["name"] == "Anonymous"


def test_the_rest_of_the_record_is_ignored(hello):
    got = hello.run({}, {"firstname": "Ada", "born": 1815})

    assert got == {"name": "Ada", "greeting": "Hello, Ada!"}


def test_shout_is_an_option_not_a_field(hello):
    record = {"firstname": "Ada", "lastname": "Lovelace"}

    assert hello.run({"shout": True}, record)["greeting"] == "HELLO, ADA LOVELACE!"
    assert hello.run({}, dict(record, shout=True))["greeting"] == "Hello, Ada Lovelace!"


def test_shouting_without_a_name(hello):
    assert hello.run({"shout": True}, {})["greeting"] == "HELLO, ANONYMOUS!"


def test_the_name_comes_from_the_record_not_the_options(hello):
    got = hello.run({"firstname": "Grace"}, {"firstname": "Ada"})

    assert got["name"] == "Ada"


def test_a_name_that_is_not_text_is_rejected(hello):
    for record in ({"firstname": 42}, {"lastname": ["Lovelace"]}):
        with pytest.raises(ArgumentError) as excinfo:
            hello.run({}, record)
        assert "must be text" in str(excinfo.value)
