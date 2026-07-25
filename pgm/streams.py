"""Turning stdin into records and script return values into stdout.

pgm owns both ends of every script: a script never reads stdin and never
prints. It receives a dict and returns a dict, a list of dicts, or a string
naming a file on disk.

Both ends are deliberately narrow. Only two things travel a pgm pipeline -- a
JSON object and a reference to a file holding JSON objects -- so any script can
read what any other script wrote. Anything else is an error rather than a
guess.
"""

import json
from pathlib import Path
from typing import Any, List, NoReturn, Optional

from .errors import InputError, OutputError

#: How many times an input may be a path pointing at another path before pgm
#: assumes it is chasing a loop.
MAX_PATH_HOPS = 10

#: Lines longer than this are never path-tested; no filesystem has names that
#: long and the stat call is pure waste on a big JSON payload.
MAX_PATH_LENGTH = 4096

def as_existing_file(text: str) -> Optional[Path]:
    """Return text as a path to an existing file, or None.

    A path is one line naming one regular file. Directories are not paths for
    pgm's purposes: a reference exists to be read, and a directory has no
    contents to read.
    """
    if not text or len(text) > MAX_PATH_LENGTH:
        return None
    if "\x00" in text or "\n" in text or "\r" in text:
        return None
    try:
        candidate = Path(text).expanduser()
        if candidate.is_file():
            return candidate
    except (OSError, ValueError):
        return None
    return None


def _describe(value: Any) -> str:
    """Quote a rejected value short enough to fit on one error line."""
    text = value if isinstance(value, str) else json.dumps(value)
    if len(text) > 60:
        text = text[:57] + "..."
    return repr(text)


def _read_file(path: Path) -> str:
    try:
        return path.read_text()
    except OSError as exc:
        raise InputError("could not read input file %s: %s" % (path, exc))
    except UnicodeDecodeError:
        raise InputError("input file %s is not text" % path)


def _reject_input(value: Any) -> NoReturn:
    raise InputError(
        "cannot read %s as input; pgm reads a JSON object, an array of JSON "
        "objects, or the path of an existing file" % _describe(value)
    )


def _parse_value(value: Any, hops: int) -> List[dict]:
    """Turn one decoded JSON value into records."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        path = as_existing_file(value)
        if path is not None:
            return _parse_text(_read_file(path), hops + 1)
    _reject_input(value)


def _parse_line(line: str, hops: int) -> List[dict]:
    """Turn one line of input into zero or more records."""
    try:
        decoded = json.loads(line)
    except ValueError:
        # Not JSON. A bare path is read as if its contents had been piped in.
        path = as_existing_file(line)
        if path is None:
            _reject_input(line)
        return _parse_text(_read_file(path), hops + 1)

    if isinstance(decoded, list):
        records = []
        for element in decoded:
            records.extend(_parse_value(element, hops))
        return records
    return _parse_value(decoded, hops)


def _parse_text(text: str, hops: int = 0) -> List[dict]:
    if hops > MAX_PATH_HOPS:
        raise InputError(
            "input kept resolving to another file after %d hops; "
            "this looks like a loop" % MAX_PATH_HOPS
        )
    records = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            records.extend(_parse_line(line, hops))
    return records


def read_records(text: str) -> List[dict]:
    """Parse raw stdin into the records to feed the script.

    No input is no records. It is the runner that decides an empty input still
    calls a per-record script once, because that rule belongs to run() and not
    to a script that asked for everything at once.
    """
    return _parse_text(text)


def render(result: Any) -> List[str]:
    """Turn a script's return value into the lines pgm writes to stdout.

    A dict is one JSON object. A list is one element per line, each element a
    JSON object or a quoted path. A string is a path, printed as it came.
    Every other return value -- None, a bare number, a set, a Path object --
    is an error: it would put something down the pipe that the next script is
    not allowed to read.
    """
    if isinstance(result, dict):
        return [_dumps(result)]
    if isinstance(result, str):
        return [_render_path(result)]
    if isinstance(result, list):
        return [_render_item(item) for item in result]
    if result is None:
        raise OutputError(
            "run() returned None; every pgm script must return a dict, a list "
            "of dicts, or the path of an existing file"
        )
    raise OutputError(
        "run() returned %s; expected a dict, a list of dicts, or the path of "
        "an existing file" % type(result).__name__
    )


def _render_item(item: Any) -> str:
    """Render one element of a returned list.

    A path element is quoted rather than printed bare, so that every line of a
    multi-line output is valid JSON on its own.
    """
    if isinstance(item, dict):
        return _dumps(item)
    if isinstance(item, str):
        return _dumps(_render_path(item))
    raise OutputError(
        "run() returned a list containing %s; every element must be a dict or "
        "the path of an existing file" % type(item).__name__
    )


def _render_path(value: str) -> str:
    """A returned string is a file reference, so it has to name a real file."""
    if as_existing_file(value) is None:
        raise OutputError(
            "run() returned the string %s, which must be one line naming an "
            "existing file" % _describe(value)
        )
    return value


def _dumps(value: Any) -> str:
    """Serialize a value, refusing anything JSON cannot represent exactly."""
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OutputError("run() returned a value that is not JSON: %s" % exc)


def read_stdin(stream) -> str:
    """Read stdin, treating an interactive terminal as no input at all."""
    try:
        if stream is None or (hasattr(stream, "isatty") and stream.isatty()):
            return ""
    except (OSError, ValueError):
        return ""
    try:
        return stream.read()
    except (OSError, ValueError) as exc:
        raise InputError("could not read stdin: %s" % exc)
    except UnicodeDecodeError:
        raise InputError("stdin is not valid text")


def write_lines(lines, stream) -> None:
    for line in lines:
        stream.write(line + "\n")
    stream.flush()
