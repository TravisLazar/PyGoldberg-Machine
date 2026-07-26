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


def echo(directory):
    """A script that hands its record straight back, to watch input arrive."""
    return script(directory, "echo", "def run(args, data):\n    return data\n")


def test_runs_the_bundled_example(workdir, monkeypatch, capsys):
    feed(monkeypatch, "")

    assert main(["hello"]) == 0
    out = capsys.readouterr().out
    assert out == '{"greeting": "Hello, Anonymous!", "name": "Anonymous"}\n'


def test_reads_stdin_into_run(workdir, monkeypatch, capsys):
    echo(workdir)
    feed(monkeypatch, '{"name": "Travis"}')

    assert main(["echo"]) == 0
    assert capsys.readouterr().out == '{"name": "Travis"}\n'


def test_run_is_called_once_per_record(workdir, monkeypatch, capsys):
    echo(workdir)
    feed(monkeypatch, '{"a": 1}\n{"a": 2}\n')

    assert main(["echo"]) == 0
    assert capsys.readouterr().out.splitlines() == ['{"a": 1}', '{"a": 2}']


def test_local_script_shadows_the_package(workdir, monkeypatch, capsys):
    script(workdir, "hello", "def run(args, data):\n    return {'local': True}\n")
    feed(monkeypatch, "")

    assert main(["hello"]) == 0
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

    assert main(["hello"]) == 1
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


def test_bundled_example_greets_the_record(workdir, monkeypatch, capsys):
    feed(monkeypatch, '{"firstname": "Ada", "lastname": "Lovelace"}')

    assert main(["hello"]) == 0
    out = capsys.readouterr().out
    assert out == '{"greeting": "Hello, Ada Lovelace!", "name": "Ada Lovelace"}\n'


def test_bundled_example_takes_its_option(workdir, monkeypatch, capsys):
    feed(monkeypatch, '{"firstname": "Ada", "lastname": "Lovelace"}')

    assert main(["--shout", "hello"]) == 0
    out = capsys.readouterr().out
    assert out == '{"greeting": "HELLO, ADA LOVELACE!", "name": "Ada Lovelace"}\n'


def test_bundled_example_greets_every_record(workdir, monkeypatch, capsys):
    feed(monkeypatch, '{"firstname": "Ada"}\n{"firstname": "Grace"}\n')

    assert main(["--shout", "hello"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert '"HELLO, ADA!"' in lines[0] and '"HELLO, GRACE!"' in lines[1]


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


def test_log_goes_to_stderr_and_leaves_the_pipeline_clean(workdir, monkeypatch, capsys):
    script(
        workdir,
        "chatty",
        "from pgm import log\n"
        "def run(args, data):\n"
        "    log('working on', data)\n"
        "    return {'ok': True}\n",
    )
    feed(monkeypatch, '{"a": 1}\n{"a": 2}\n')

    assert main(["chatty"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"ok": true}\n{"ok": true}\n'
    assert captured.err == (
        "chatty: working on {'a': 1}\nchatty: working on {'a': 2}\n"
    )


def test_a_script_can_call_another(workdir, monkeypatch, capsys):
    script(
        workdir,
        "dice",
        "from pgm import call, log\n"
        "def run(args, data):\n"
        "    log('rolling')\n"
        "    rolls = call('randint', count=2, start=1, end=1)\n"
        "    return [{'roll': r['value']} for r in rolls]\n",
    )
    feed(monkeypatch, "")

    assert main(["dice"]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"roll": 1}\n{"roll": 1}\n'
    # The caller does the talking again once the callee is done.
    assert captured.err == "dice: rolling\n"


def test_a_bad_option_type_reads_as_a_plain_error(workdir, monkeypatch, capsys):
    feed(monkeypatch, "")

    assert main(["--count=lots", "randint"]) == 1
    err = capsys.readouterr().err
    assert err == "pgm: --count must be a whole number, got 'lots'\n"


def histogram(directory):
    """A script that cannot answer until it has seen every record."""
    return script(
        directory,
        "histogram",
        "def run_all(args, records):\n"
        "    counts = {}\n"
        "    for record in records:\n"
        "        counts[record['bucket']] = counts.get(record['bucket'], 0) + 1\n"
        "    return counts\n",
    )


def test_run_all_sees_every_record_at_once(workdir, monkeypatch, capsys):
    histogram(workdir)
    feed(monkeypatch, '{"bucket": "a"}\n{"bucket": "b"}\n{"bucket": "a"}\n')

    assert main(["histogram"]) == 0
    assert capsys.readouterr().out == '{"a": 2, "b": 1}\n'


def test_run_all_gets_nothing_when_there_is_nothing(workdir, monkeypatch, capsys):
    script(
        workdir,
        "counter",
        "def run_all(args, records):\n    return {'seen': len(records)}\n",
    )
    feed(monkeypatch, "")

    # Not one empty record: there is no histogram of one blank row.
    assert main(["counter"]) == 0
    assert capsys.readouterr().out == '{"seen": 0}\n'


def test_run_all_takes_options_like_anything_else(workdir, monkeypatch, capsys):
    script(
        workdir,
        "total",
        "def run_all(args, records):\n"
        "    scale = args.get('scale', 1)\n"
        "    return {'total': sum(r['n'] for r in records) * scale}\n",
    )
    feed(monkeypatch, '{"n": 1}\n{"n": 2}\n')

    assert main(["--scale=10", "total"]) == 0
    assert capsys.readouterr().out == '{"total": 30}\n'


def test_run_all_can_still_fan_out(workdir, monkeypatch, capsys):
    script(
        workdir,
        "sort_them",
        "def run_all(args, records):\n"
        "    return sorted(records, key=lambda r: r['n'])\n",
    )
    feed(monkeypatch, '{"n": 2}\n{"n": 1}\n')

    assert main(["sort_them"]) == 0
    assert capsys.readouterr().out.splitlines() == ['{"n": 1}', '{"n": 2}']


def test_a_pipeline_ending_in_run_all(workdir, monkeypatch, capsys):
    histogram(workdir)
    script(
        workdir,
        "buckets",
        "def run(args, data):\n"
        "    return [{'bucket': b} for b in ('a', 'b', 'a')]\n",
    )
    feed(monkeypatch, "")
    assert main(["buckets"]) == 0
    piped = capsys.readouterr().out

    feed(monkeypatch, piped)
    assert main(["histogram"]) == 0
    assert capsys.readouterr().out == '{"a": 2, "b": 1}\n'


def test_bundled_groupcount_tallies_a_pipeline(workdir, monkeypatch, capsys):
    feed(monkeypatch, "")
    assert main(["--count=5", "--start=1", "--end=1", "randint"]) == 0
    piped = capsys.readouterr().out

    feed(monkeypatch, piped)
    assert main(["--groupname=value", "groupcount"]) == 0
    assert capsys.readouterr().out == '{"count": 5, "value": 1}\n'


def test_bundled_groupcount_needs_its_option(workdir, monkeypatch, capsys):
    feed(monkeypatch, '{"a": 1}\n')

    assert main(["groupcount"]) == 1
    assert "--groupname is required" in capsys.readouterr().err


def test_bundled_sortlist_orders_a_pipeline(workdir, monkeypatch, capsys):
    feed(monkeypatch, '[{"n": 2}, {"n": 1}, {"n": 3}]')

    assert main(["--sortkeys=n", "sortlist"]) == 0
    assert capsys.readouterr().out.splitlines() == ['{"n": 1}', '{"n": 2}', '{"n": 3}']


def test_bundled_sortlist_takes_a_direction(workdir, monkeypatch, capsys):
    feed(monkeypatch, '[{"n": 2}, {"n": 1}, {"n": 3}]')

    assert main(["--sortkeys=n", "--order=desc", "sortlist"]) == 0
    assert capsys.readouterr().out.splitlines() == ['{"n": 3}', '{"n": 2}', '{"n": 1}']


def test_bundled_sortlist_needs_its_option(workdir, monkeypatch, capsys):
    feed(monkeypatch, '{"n": 1}\n')

    assert main(["sortlist"]) == 1
    assert "--sortkeys is required" in capsys.readouterr().err


def test_defining_both_entry_points_is_rejected(workdir, monkeypatch, capsys):
    script(
        workdir,
        "greedy",
        "def run(args, data):\n    return {}\n"
        "def run_all(args, records):\n    return {}\n",
    )
    feed(monkeypatch, "")

    assert main(["greedy"]) == 1
    assert "defines both run() and run_all()" in capsys.readouterr().err


def test_run_all_with_the_wrong_signature_is_rejected(workdir, monkeypatch, capsys):
    script(workdir, "broken", "def run_all(records):\n    return {}\n")
    feed(monkeypatch, "")

    assert main(["broken"]) == 1
    err = capsys.readouterr().err
    assert "cannot be called as run_all(args: dict, records: list)" in err


def test_a_script_with_neither_entry_point_says_so(workdir, monkeypatch, capsys):
    script(workdir, "empty", "x = 1\n")
    feed(monkeypatch, "")

    assert main(["empty"]) == 1
    err = capsys.readouterr().err
    assert "run(args: dict, data: dict) or run_all(args: dict, records: list)" in err


def test_a_raising_run_all_is_reported(workdir, monkeypatch, capsys):
    script(workdir, "boom", "def run_all(args, records):\n    raise KeyError('nope')\n")
    feed(monkeypatch, '{"a": 1}\n')

    assert main(["boom"]) == 1
    assert "boom.py raised KeyError" in capsys.readouterr().err


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
    out = capsys.readouterr().out
    assert "hello" in out
    assert "randint" in out


def rows(out, qualname):
    """Every listing line naming this script, in the order they were printed."""
    return [line for line in out.splitlines() if line[1:].split(None, 1)[0] == qualname]


def row(out, qualname):
    """The one listing line naming this script."""
    return rows(out, qualname)[0]


def test_list_says_what_each_script_is_and_does(workdir, monkeypatch, capsys):
    script(
        workdir,
        "chart",
        '"""Draw a histogram of everything that came in."""\n'
        "def run_all(args, records):\n    return {}\n",
    )
    script(workdir, "plain", "def run(args, data):\n    return data\n")

    assert main(["--list"]) == 0
    out = capsys.readouterr().out

    chart = row(out, "chart")
    assert "run_all" in chart
    assert chart.endswith("Draw a histogram of everything that came in.")
    assert "local" in chart

    # No docstring, nothing to say -- and no trailing whitespace either.
    assert row(out, "plain").endswith("local")
    assert "run_all" not in row(out, "plain")


def nested(workdir, monkeypatch, folder, name, body):
    """Put a script in a folder of its own, on the search path."""
    monkeypatch.setenv(discovery.PGM_PATHS_ENV, str(workdir / "env"))
    directory = workdir / "env" / folder
    directory.mkdir(parents=True, exist_ok=True)
    return script(directory, name, body)


def test_list_names_a_script_by_the_folder_it_is_in(workdir, monkeypatch, capsys):
    nested(
        workdir,
        monkeypatch,
        "generators",
        "thing",
        '"""One of the generators."""\ndef run(args, data):\n    return data\n',
    )

    assert main(["--list"]) == 0
    out = capsys.readouterr().out

    assert row(out, "generators/thing").endswith("One of the generators.")


def test_list_still_marks_what_is_shadowed(workdir, monkeypatch, capsys):
    nested(
        workdir,
        monkeypatch,
        "generators",
        "thing",
        '"""The one in a folder."""\ndef run(args, data):\n    return data\n',
    )
    script(workdir, "thing", '"""Mine, in front of it."""\ndef run(args, data):\n    return {}\n')

    assert main(["--list"]) == 0
    out = capsys.readouterr().out

    mine = row(out, "thing")
    shadowed = row(out, "generators/thing")
    assert mine.startswith(" ") and mine.endswith("Mine, in front of it.")
    assert shadowed.startswith("#")


def test_list_marks_a_name_that_two_folders_claim(workdir, monkeypatch, capsys):
    monkeypatch.setenv(discovery.PGM_PATHS_ENV, str(workdir / "env"))
    for folder in ("generators", "parsers"):
        directory = workdir / "env" / folder
        directory.mkdir(parents=True)
        (directory / "thing.py").write_text("def run(args, data):\n    return data\n")

    assert main(["--list"]) == 0
    out = capsys.readouterr().out

    # Neither is what `pgm thing` resolves to, so neither is marked active.
    assert row(out, "generators/thing").startswith("#")
    assert row(out, "parsers/thing").startswith("#")


def test_list_does_not_run_the_scripts_it_lists(workdir, monkeypatch, capsys):
    script(workdir, "loud", "raise SystemExit('never')\ndef run(args, data):\n    return data\n")

    assert main(["--list"]) == 0
    assert "loud" in capsys.readouterr().out


def test_no_arguments_prints_help(workdir, capsys):
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


def documented(directory):
    """A script with something to say for itself."""
    return script(
        directory,
        "chart",
        '"""Draw a histogram.\n'
        "\n"
        "    $ pgm chart --bins=20\n"
        "\n"
        'Bins default to ten.\n'
        '"""\n'
        "def run_all(args, records):\n    return {}\n",
    )


def test_help_alone_is_pgms_own(workdir, capsys):
    # With no script to add, argparse prints and exits, as it always has.
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "--traceback" in out
    assert "---------" not in out


def test_help_for_a_script_adds_what_the_script_says(workdir, capsys):
    documented(workdir)

    assert main(["chart", "--help"]) == 0
    out = capsys.readouterr().out

    # pgm's own help, then a divider, then the script's docstring entire.
    assert "usage:" in out
    assert "--traceback" in out
    pgm_help, _, script_help = out.partition("---------")
    assert "--traceback" in pgm_help
    assert "Draw a histogram." in script_help
    assert "$ pgm chart --bins=20" in script_help
    assert "Bins default to ten." in script_help


def test_help_for_a_script_names_it_and_says_what_it_is(workdir, capsys):
    path = documented(workdir)

    assert main(["chart", "--help"]) == 0
    out = capsys.readouterr().out

    assert "chart  run_all  %s" % path in out


def test_help_does_not_care_where_the_option_sits(workdir, capsys):
    documented(workdir)

    assert main(["--help", "chart"]) == 0
    assert "Draw a histogram." in capsys.readouterr().out


def test_the_short_help_option_works_the_same(workdir, capsys):
    documented(workdir)

    assert main(["-h", "chart"]) == 0
    assert "Draw a histogram." in capsys.readouterr().out


def test_help_for_a_script_that_says_nothing(workdir, capsys):
    script(workdir, "silent", "def run(args, data):\n    return data\n")

    assert main(["silent", "--help"]) == 0
    out = capsys.readouterr().out

    assert "usage:" in out
    assert "silent.py has no docstring" in out


def test_help_for_a_script_that_is_not_there(workdir, capsys):
    assert main(["nope", "--help"]) == 1
    captured = capsys.readouterr()

    # The complaint, and not underneath a page of help nobody asked for.
    assert "no script named 'nope'" in captured.err
    assert captured.out == ""


def test_help_does_not_run_the_script(workdir, capsys):
    script(
        workdir,
        "loud",
        '"""Says nothing at import."""\n'
        "raise SystemExit('never')\n"
        "def run(args, data):\n    return data\n",
    )

    assert main(["loud", "--help"]) == 0
    assert "Says nothing at import." in capsys.readouterr().out


def test_help_beats_running_the_script(workdir, monkeypatch, capsys):
    documented(workdir)
    feed(monkeypatch, '{"a": 1}\n')

    assert main(["chart", "--help", "--bins=3"]) == 0
    out = capsys.readouterr().out
    assert "Draw a histogram." in out
    assert '{"a": 1}' not in out


def test_pipeline_between_two_scripts(workdir, monkeypatch, capsys):
    script(
        workdir,
        "fan_out",
        "def run(args, data):\n    return [{'n': n} for n in (1, 2)]\n",
    )
    script(workdir, "double", "def run(args, data):\n    return {'n': data['n'] * 2}\n")
    feed(monkeypatch, "")
    assert main(["fan_out"]) == 0
    piped = capsys.readouterr().out

    feed(monkeypatch, piped)
    assert main(["double"]) == 0
    assert capsys.readouterr().out.splitlines() == ['{"n": 2}', '{"n": 4}']


def test_bundled_randint_fans_out(workdir, monkeypatch, capsys):
    feed(monkeypatch, "")

    assert main(["--count=3", "--start=7", "--end=7", "randint"]) == 0
    assert capsys.readouterr().out.splitlines() == ['{"value": 7}'] * 3


def test_file_reference_flows_through_a_pipeline(workdir, monkeypatch, capsys):
    payload = workdir / "payload.json"
    payload.write_text('{"name": "from-disk"}')
    script(
        workdir,
        "emit_path",
        "def run(args, data):\n    return %r\n" % str(payload),
    )
    echo(workdir)
    feed(monkeypatch, "")
    assert main(["emit_path"]) == 0
    piped = capsys.readouterr().out
    assert piped.strip() == str(payload)

    feed(monkeypatch, piped)
    assert main(["echo"]) == 0
    assert capsys.readouterr().out == '{"name": "from-disk"}\n'
