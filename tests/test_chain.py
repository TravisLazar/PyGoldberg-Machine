import pytest

from pgm import call, discovery
from pgm.chain import MAX_CALL_DEPTH
from pgm.errors import InvalidScriptError, OutputError, ScriptNotFoundError
from pgm.helpers import script_name, set_script_name
from pgm.runner import ScriptFailedError


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(discovery.PGM_PATHS_ENV, raising=False)
    set_script_name(None)
    yield tmp_path
    set_script_name(None)


def script(directory, name, body):
    path = directory / ("%s.py" % name)
    path.write_text(body)
    return path


def test_calls_a_bundled_script_with_options():
    got = call("randint", count=3, start=7, end=7)

    assert got == [{"value": 7}, {"value": 7}, {"value": 7}]


def test_no_data_means_one_call_with_an_empty_record(workdir):
    script(workdir, "seen", "def run(args, data):\n    return {'seen': data}\n")

    assert call("seen") == [{"seen": {}}]


def test_one_record_in_one_call(workdir):
    script(workdir, "seen", "def run(args, data):\n    return {'seen': data}\n")

    assert call("seen", {"a": 1}) == [{"seen": {"a": 1}}]


def test_many_records_mean_many_calls(workdir):
    script(workdir, "double", "def run(args, data):\n    return {'n': data['n'] * 2}\n")

    assert call("double", [{"n": 1}, {"n": 2}]) == [{"n": 2}, {"n": 4}]


def test_options_reach_the_called_script(workdir):
    script(workdir, "opts", "def run(args, data):\n    return args\n")

    assert call("opts", None, factor=1.5, dry=True) == [{"factor": 1.5, "dry": True}]


def test_an_option_may_be_named_like_a_parameter(workdir):
    script(workdir, "opts", "def run(args, data):\n    return args\n")

    assert call("opts", None, script="x", data="y") == [{"script": "x", "data": "y"}]


def test_a_returned_list_is_flattened(workdir):
    script(workdir, "fan", "def run(args, data):\n    return [{'n': 1}, {'n': 2}]\n")

    assert call("fan") == [{"n": 1}, {"n": 2}]


def test_a_returned_path_is_read_back(workdir):
    payload = workdir / "payload.json"
    payload.write_text('{"from": "disk"}')
    script(workdir, "emit", "def run(args, data):\n    return %r\n" % str(payload))

    assert call("emit") == [{"from": "disk"}]


def test_a_script_that_produces_nothing(workdir):
    script(workdir, "empty", "def run(args, data):\n    return []\n")

    assert call("empty") == []


def test_no_records_in_means_no_calls(workdir):
    script(workdir, "boom", "def run(args, data):\n    raise AssertionError\n")

    assert call("boom", []) == []


def test_a_chain_of_two_scripts(workdir):
    script(workdir, "double", "def run(args, data):\n    return {'n': data['n'] * 2}\n")
    script(
        workdir,
        "pipeline",
        "from pgm import call\n"
        "def run(args, data):\n"
        "    return call('double', call('double', [{'n': 1}, {'n': 2}]))\n",
    )

    assert call("pipeline") == [{"n": 4}, {"n": 8}]


def test_calling_a_script_that_takes_every_record_at_once(workdir):
    script(
        workdir,
        "total",
        "def run_all(args, records):\n"
        "    return {'total': sum(r['n'] for r in records)}\n",
    )

    assert call("total", [{"n": 1}, {"n": 2}, {"n": 3}]) == [{"total": 6}]


def test_calling_an_aggregator_with_no_records(workdir):
    script(
        workdir,
        "total",
        "def run_all(args, records):\n"
        "    return {'total': sum(r['n'] for r in records)}\n",
    )

    assert call("total", []) == [{"total": 0}]
    assert call("total") == [{"total": 0}]


def test_an_aggregator_can_be_the_end_of_a_chain(workdir):
    script(workdir, "total", "def run_all(args, records):\n    return {'n': len(records)}\n")
    script(
        workdir,
        "pipeline",
        "from pgm import call\n"
        "def run(args, data):\n"
        "    return call('total', call('randint', count=4, start=1, end=1))\n",
    )

    assert call("pipeline") == [{"n": 4}]


def test_the_called_script_is_held_to_the_output_contract(workdir):
    script(workdir, "bad", "def run(args, data):\n    return 42\n")

    with pytest.raises(OutputError):
        call("bad")


def test_a_raising_script_names_itself(workdir):
    script(workdir, "boom", "def run(args, data):\n    raise KeyError('nope')\n")

    with pytest.raises(ScriptFailedError) as excinfo:
        call("boom")
    assert "boom.py raised KeyError" in str(excinfo.value)


def test_an_unknown_script_is_reported(workdir):
    with pytest.raises(ScriptNotFoundError):
        call("nope")


def test_data_has_to_be_records(workdir):
    script(workdir, "seen", "def run(args, data):\n    return {'seen': data}\n")

    with pytest.raises(TypeError) as excinfo:
        call("seen", "just a string")
    assert "takes one record, a list of records, or nothing" in str(excinfo.value)

    with pytest.raises(TypeError) as excinfo:
        call("seen", [{"a": 1}, "nope"])
    assert "every record has to be a dict" in str(excinfo.value)


def test_a_loop_between_scripts_is_caught(workdir):
    script(
        workdir,
        "ping",
        "from pgm import call\ndef run(args, data):\n    return call('pong')\n",
    )
    script(
        workdir,
        "pong",
        "from pgm import call\ndef run(args, data):\n    return call('ping')\n",
    )

    with pytest.raises(InvalidScriptError) as excinfo:
        call("ping")
    assert "this looks like a loop" in str(excinfo.value)
    assert "ping -> pong" in str(excinfo.value)


def test_the_depth_limit_leaves_room_for_real_nesting(workdir):
    script(workdir, "leaf", "def run(args, data):\n    return {'depth': 0}\n")
    previous = "leaf"
    for depth in range(1, MAX_CALL_DEPTH):
        name = "step%d" % depth
        script(
            workdir,
            name,
            "from pgm import call\n"
            "def run(args, data):\n"
            "    return {'depth': call(%r)[0]['depth'] + 1}\n" % previous,
        )
        previous = name

    assert call(previous) == [{"depth": MAX_CALL_DEPTH - 1}]


def test_the_caller_gets_its_log_name_back(workdir):
    script(workdir, "quiet", "def run(args, data):\n    return {}\n")
    set_script_name("caller")

    call("quiet")

    assert script_name() == "caller"


def test_a_called_script_is_imported_once(workdir, capsys):
    script(
        workdir,
        "counted",
        "import sys\n"
        "sys.stderr.write('imported\\n')\n"
        "def run(args, data):\n    return {}\n",
    )

    call("counted")
    call("counted")

    assert capsys.readouterr().err.count("imported") == 1
