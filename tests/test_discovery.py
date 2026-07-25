import os

import pytest

from pgm import discovery
from pgm.errors import PgmError, ScriptNotFoundError


def write_script(directory, name, body="def run(args, data):\n    return data\n"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("%s.py" % name)
    path.write_text(body)
    return path


def test_local_directory_wins(tmp_path, monkeypatch):
    local = tmp_path / "local"
    other = tmp_path / "other"
    expected = write_script(local, "thing")
    write_script(other, "thing")
    monkeypatch.chdir(local)
    monkeypatch.setenv(discovery.PGM_PATHS_ENV, str(other))

    assert discovery.find_script("thing") == expected


def test_env_paths_win_over_package(tmp_path, monkeypatch):
    env_dir = tmp_path / "env"
    expected = write_script(env_dir, "hello")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(discovery.PGM_PATHS_ENV, str(env_dir))

    assert discovery.find_script("hello") == expected


def test_env_paths_are_searched_in_order(tmp_path, monkeypatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    expected = write_script(first, "thing")
    write_script(second, "thing")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        discovery.PGM_PATHS_ENV, os.pathsep.join([str(first), str(second)])
    )

    assert discovery.find_script("thing") == expected


def test_package_scripts_are_the_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(discovery.PGM_PATHS_ENV, raising=False)

    found = discovery.find_script("hello")
    assert found == discovery.bundled_scripts_dir() / "hello.py"


def test_missing_script_lists_search_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(discovery.PGM_PATHS_ENV, raising=False)

    with pytest.raises(ScriptNotFoundError) as excinfo:
        discovery.find_script("nope")
    assert str(tmp_path) in str(excinfo.value)


def test_explicit_py_suffix_is_accepted(tmp_path, monkeypatch):
    expected = write_script(tmp_path, "thing")
    monkeypatch.chdir(tmp_path)

    assert discovery.find_script("thing.py") == expected


def test_paths_are_rejected_as_names():
    with pytest.raises(PgmError):
        discovery.script_filename("some/where")


def test_empty_name_is_rejected():
    with pytest.raises(PgmError):
        discovery.script_filename("  ")


def test_listing_carries_what_each_script_says_about_itself(tmp_path, monkeypatch):
    local = tmp_path / "local"
    write_script(
        local,
        "chart",
        '"""Draw a histogram."""\ndef run_all(args, records):\n    return {}\n',
    )
    monkeypatch.chdir(local)
    monkeypatch.delenv(discovery.PGM_PATHS_ENV, raising=False)

    entry = next(e for e in discovery.list_scripts() if e["name"] == "chart")

    assert entry["entry"] == "run_all"
    assert entry["summary"] == "Draw a histogram."
    assert entry["source"] == "local"
    assert entry["path"].endswith("chart.py")


def test_listing_marks_shadowed_scripts(tmp_path, monkeypatch):
    local = tmp_path / "local"
    write_script(local, "hello")
    monkeypatch.chdir(local)
    monkeypatch.delenv(discovery.PGM_PATHS_ENV, raising=False)

    entries = [e for e in discovery.list_scripts() if e["name"] == "hello"]
    assert [e["source"] for e in entries] == ["local", "package"]
    assert [e["active"] for e in entries] == [True, False]
