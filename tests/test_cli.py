import io

import pytest

from pgm import discovery
from pgm.cli import main


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(discovery.PGM_PATHS_ENV, raising=False)
    return tmp_path


def script(directory, name, body):
    path = directory / ("%s.py" % name)
    path.write_text(body)
    return path


def feed(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_runs_the_bundled_example(workdir, monkeypatch, capsys):
    feed(monkeypatch, "")

    assert main(["hello_world"]) == 0
    assert capsys.readouterr().out == '{"greeting": "Hello, world!", "name": "world"}\n'


def test_reads_stdin_into_run(workdir, monkeypatch, capsys):
    feed(monkeypatch, '{"name": "Travis"}')

    assert main(["hello_world"]) == 0
    assert '"Hello, Travis!"' in capsys.readouterr().out


def test_run_is_called_once_per_record(workdir, monkeypatch, capsys):
    feed(monkeypatch, '{"name": "a"}\n{"name": "b"}\n')

    assert main(["hello_world"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert '"Hello, a!"' in lines[0] and '"Hello, b!"' in lines[1]


def test_local_script_shadows_the_package(workdir, monkeypatch, capsys):
    script(workdir, "hello_world", "def run(args, data):\n    return {'local': True}\n")
    feed(monkeypatch, "")

    assert main(["hello_world"]) == 0
    assert capsys.readouterr().out == '{"local": true}\n'


def test_missing_script_exits_nonzero(workdir, monkeypatch, capsys):
    feed(monkeypatch, "")

    assert main(["nope"]) == 1
    assert "no script named 'nope'" in capsys.readouterr().err


def test_script_without_run_is_rejected(workdir, monkeypatch, capsys):
    script(workdir, "broken", "x = 1\n")
    feed(monkeypatch, "")

    assert main(["broken"]) == 1
    assert "defines no run()" in capsys.readouterr().err


def test_script_with_wrong_signature_is_rejected(workdir, monkeypatch, capsys):
    script(workdir, "broken", "def run():\n    return {}\n")
    feed(monkeypatch, "")

    assert main(["broken"]) == 1
    assert "cannot be called" in capsys.readouterr().err


def test_script_taking_only_data_is_rejected(workdir, monkeypatch, capsys):
    script(workdir, "old", "def run(data):\n    return data\n")
    feed(monkeypatch, "")

    assert main(["old"]) == 1
    assert "cannot be called as run(args: dict, data: dict)" in capsys.readouterr().err


def test_import_failure_is_reported(workdir, monkeypatch, capsys):
    script(workdir, "broken", "raise ValueError('boom')\n")
    feed(monkeypatch, "")

    assert main(["broken"]) == 1
    assert "failed to import" in capsys.readouterr().err


def test_raising_script_is_reported(workdir, monkeypatch, capsys):
    script(workdir, "boom", "def run(args, data):\n    raise KeyError('nope')\n")
    feed(monkeypatch, "")

    assert main(["boom"]) == 1
    assert "boom.py raised KeyError" in capsys.readouterr().err


def test_bad_return_type_is_reported(workdir, monkeypatch, capsys):
    script(workdir, "bad", "def run(args, data):\n    return 42\n")
    feed(monkeypatch, "")

    assert main(["bad"]) == 1
    assert "expected a dict" in capsys.readouterr().err


def test_none_return_is_reported(workdir, monkeypatch, capsys):
    script(workdir, "sink", "def run(args, data):\n    return None\n")
    feed(monkeypatch, "")

    assert main(["sink"]) == 1
    assert "returned None" in capsys.readouterr().err


def test_unreadable_stdin_is_reported(workdir, monkeypatch, capsys):
    feed(monkeypatch, "just words\n")

    assert main(["hello_world"]) == 1
    err = capsys.readouterr().err
    assert "cannot read 'just words' as input" in err


def show_args(workdir):
    """A script that just prints the args it was handed."""
    return script(workdir, "show", "def run(args, data):\n    return args\n")


def test_options_before_the_script_reach_it(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["--dry", "show"]) == 0
    assert capsys.readouterr().out == '{"dry": true}\n'


def test_inline_value_reaches_the_script(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["--verbosity=3", "show"]) == 0
    assert capsys.readouterr().out == '{"verbosity": 3}\n'


def test_string_value_reaches_the_script(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["--logpath=path/to/file", "show"]) == 0
    assert capsys.readouterr().out == '{"logpath": "path/to/file"}\n'


def test_options_after_the_script_reach_it(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["show", "--dry", "--logpath=out.txt"]) == 0
    assert capsys.readouterr().out == '{"dry": true, "logpath": "out.txt"}\n'


def test_separate_value_is_reported_with_the_fix(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["--logpath", "out.txt", "show"]) == 1
    assert "did you mean --logpath=out.txt?" in capsys.readouterr().err


def test_script_with_no_options_gets_an_empty_dict(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["show"]) == 0
    assert capsys.readouterr().out == "{}\n"


def test_pgm_options_do_not_reach_the_script(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["--traceback", "show"]) == 0
    assert capsys.readouterr().out == "{}\n"


def test_the_same_options_reach_every_record(workdir, monkeypatch, capsys):
    script(
        workdir,
        "merge",
        "def run(args, data):\n    return dict(data, seen=args['tag'])\n",
    )
    feed(monkeypatch, '{"a": 1}\n{"a": 2}\n')

    assert main(["--tag=x", "merge"]) == 0
    assert capsys.readouterr().out == '{"a": 1, "seen": "x"}\n{"a": 2, "seen": "x"}\n'


def test_a_script_cannot_leak_args_into_the_next_record(workdir, monkeypatch, capsys):
    script(
        workdir,
        "leaky",
        "def run(args, data):\n"
        "    seen = args.pop('tag', 'gone')\n"
        "    return {'seen': seen}\n",
    )
    feed(monkeypatch, '{"a": 1}\n{"a": 2}\n')

    assert main(["--tag=x", "leaky"]) == 0
    assert capsys.readouterr().out == '{"seen": "x"}\n{"seen": "x"}\n'


def test_bundled_example_takes_an_option(workdir, monkeypatch, capsys):
    feed(monkeypatch, "")

    assert main(["--shout", "hello_world"]) == 0
    assert '"HELLO, WORLD!"' in capsys.readouterr().out


def test_repeated_option_is_reported(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["--tag=a", "--tag=b", "show"]) == 1
    assert "more than once" in capsys.readouterr().err


def test_extra_bare_word_is_reported(workdir, monkeypatch, capsys):
    show_args(workdir)
    feed(monkeypatch, "")

    assert main(["show", "extra"]) == 1
    assert "one script at a time" in capsys.readouterr().err


def test_where_reports_the_resolved_file(workdir, monkeypatch, capsys):
    path = script(workdir, "thing", "def run(args, data):\n    return {}\n")
    feed(monkeypatch, "")

    assert main(["--where", "thing"]) == 0
    assert capsys.readouterr().out.strip() == str(path)


def test_paths_reports_the_search_order(workdir, monkeypatch, capsys):
    monkeypatch.setenv(discovery.PGM_PATHS_ENV, "/somewhere")

    assert main(["--paths"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == str(workdir)
    assert out[1] == "/somewhere"
    assert out[2] == str(discovery.bundled_scripts_dir())


def test_list_shows_bundled_scripts(workdir, monkeypatch, capsys):
    assert main(["--list"]) == 0
    assert "hello_world" in capsys.readouterr().out


def test_no_arguments_prints_help(workdir, capsys):
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_pipeline_between_two_scripts(workdir, monkeypatch, capsys):
    script(
        workdir,
        "fan_out",
        "def run(args, data):\n    return [{'name': n} for n in ('a', 'b')]\n",
    )
    feed(monkeypatch, "")
    assert main(["fan_out"]) == 0
    piped = capsys.readouterr().out

    feed(monkeypatch, piped)
    assert main(["hello_world"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert '"Hello, a!"' in out[0] and '"Hello, b!"' in out[1]


def test_file_reference_flows_through_a_pipeline(workdir, monkeypatch, capsys):
    payload = workdir / "payload.json"
    payload.write_text('{"name": "from-disk"}')
    script(
        workdir,
        "emit_path",
        "def run(args, data):\n    return %r\n" % str(payload),
    )
    feed(monkeypatch, "")
    assert main(["emit_path"]) == 0
    piped = capsys.readouterr().out
    assert piped.strip() == str(payload)

    feed(monkeypatch, piped)
    assert main(["hello_world"]) == 0
    assert '"Hello, from-disk!"' in capsys.readouterr().out
