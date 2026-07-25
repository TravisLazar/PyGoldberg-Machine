from pgm.runner import ENTRY_BOTH, ENTRY_NONE, ENTRY_UNREADABLE, MAX_SUMMARY, describe


def script(tmp_path, body, name="thing.py"):
    path = tmp_path / name
    path.write_text(body)
    return path


def test_the_summary_is_the_first_docstring_line(tmp_path):
    path = script(
        tmp_path,
        '"""Chart everything that came in.\n\nA longer explanation nobody needs in a listing.\n"""\n'
        "def run_all(args, records):\n    return {}\n",
    )

    assert describe(path)["summary"] == "Chart everything that came in."


def test_a_script_with_no_docstring_says_nothing(tmp_path):
    path = script(tmp_path, "def run(args, data):\n    return data\n")

    assert describe(path)["summary"] == ""


def test_a_long_summary_is_cut_down(tmp_path):
    path = script(tmp_path, '"""%s"""\ndef run(args, data):\n    return data\n' % ("x" * 200))

    summary = describe(path)["summary"]
    assert len(summary) == MAX_SUMMARY
    assert summary.endswith("...")


def test_a_summary_that_just_fits_is_left_alone(tmp_path):
    path = script(tmp_path, '"""%s"""\ndef run(args, data):\n    return data\n' % ("x" * MAX_SUMMARY))

    assert describe(path)["summary"] == "x" * MAX_SUMMARY


def test_which_entry_point_a_script_defines(tmp_path):
    one = script(tmp_path, "def run(args, data):\n    return data\n", "one.py")
    every = script(tmp_path, "def run_all(args, records):\n    return {}\n", "every.py")

    assert describe(one)["entry"] == "run"
    assert describe(every)["entry"] == "run_all"


def test_an_async_entry_point_still_counts(tmp_path):
    path = script(tmp_path, "async def run_all(args, records):\n    return {}\n")

    assert describe(path)["entry"] == "run_all"


def test_an_entry_point_that_was_assigned_still_counts(tmp_path):
    path = script(tmp_path, "def greet(args, data):\n    return data\nrun = greet\n")

    assert describe(path)["entry"] == "run"


def test_a_file_defining_both_is_shown_as_both(tmp_path):
    path = script(
        tmp_path,
        "def run(args, data):\n    return data\ndef run_all(args, records):\n    return {}\n",
    )

    assert describe(path)["entry"] == ENTRY_BOTH


def test_a_file_that_is_not_a_script(tmp_path):
    path = script(tmp_path, "x = 1\n")

    assert describe(path)["entry"] == ENTRY_NONE


def test_a_nested_run_does_not_count(tmp_path):
    path = script(tmp_path, "def outer():\n    def run(args, data):\n        return data\n")

    assert describe(path)["entry"] == ENTRY_NONE


def test_a_file_pgm_cannot_parse(tmp_path):
    path = script(tmp_path, "def run(args, data:\n")

    assert describe(path) == {"summary": "", "entry": ENTRY_UNREADABLE}


def test_a_file_that_is_not_there(tmp_path):
    assert describe(tmp_path / "gone.py")["entry"] == ENTRY_UNREADABLE


def test_describing_a_script_does_not_run_it(tmp_path, capsys):
    path = script(
        tmp_path,
        "import sys\n"
        "sys.stderr.write('side effect\\n')\n"
        "raise SystemExit(1)\n"
        "def run(args, data):\n    return data\n",
    )

    assert describe(path)["entry"] == "run"
    assert capsys.readouterr().err == ""
