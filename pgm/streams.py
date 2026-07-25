"""Turning stdin into records and script return values into stdout.

pgm owns both ends of every script: a script never reads stdin and never
prints. It receives a dict and returns a dict, a list of dicts, a set, or a
string that names a file on disk.
"""

import json
from pathlib import Path
from typing import Any, List, Optional

from .errors import InputError, OutputError

#: Non-JSON input lines are handed to run() under this key.
VALUE_KEY = "value"

#: How many times an input may be a path pointing at another path before pgm
#: assumes it is chasing a loop.
MAX_PATH_HOPS = 10

#: Lines longer than this are never path-tested; no filesystem has names that
#: long and the stat call is pure waste on a big JSON payload.
MAX_PATH_LENGTH = 4096


def as_existing_file(text: str) -> Optional[Path]:
    """Return text as a path to an existing file, or None."""
    if not text or len(text) > MAX_PATH_LENGTH or "\x00" in text:
        return None
    try:
        candidate = Path(text).expanduser()
        if candidate.is_file():
            return candidate
    except (OSError, ValueError):
        return None
    return None


def _read_file(path: Path) -> str:
    try:
        return path.read_text()
    except OSError as exc:
        raise InputError("could not read input file %s: %s" % (path, exc))
    except UnicodeDecodeError:
        raise InputError("input file %s is not text" % path)


def _record(value: Any) -> dict:
    """Wrap a decoded value so run() always receives a dict."""
    if isinstance(value, dict):
        return value
    return {VALUE_KEY: value}


def _parse_line(line: str, hops: int) -> List[dict]:
    """Turn one line of input into zero or more records."""
    try:
        decoded = json.loads(line)
    except ValueError:
        # Not JSON. A bare path is read as if its contents had been piped in.
        path = as_existing_file(line)
        if path is not None:
            return _parse_text(_read_file(path), hops + 1)
        return [{VALUE_KEY: line}]

    if isinstance(decoded, list):
        return [_record(item) for item in decoded]
    if isinstance(decoded, str):
        path = as_existing_file(decoded)
        if path is not None:
            return _parse_text(_read_file(path), hops + 1)
    return [_record(decoded)]


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
    """Parse raw stdin into the records to feed run(), one call per record.

    Empty input yields a single empty record so that scripts which need no
    input still run exactly once.
    """
    records = _parse_text(text)
    return records or [{}]


def render(result: Any) -> List[str]:
    """Turn a script's return value into the lines pgm writes to stdout."""
    if result is None:
        return []
    if isinstance(result, dict):
        return [_dumps(result)]
    if isinstance(result, str):
        return [_render_path(result)]
    if isinstance(result, (set, frozenset)):
        # Sets have no order of their own; sort so a pipeline is reproducible.
        return sorted(_render_element(item, as_json=False) for item in result)
    if isinstance(result, (list, tuple)):
        return [_render_element(item, as_json=True) for item in result]
    raise OutputError(
        "run() returned %s; expected a dict, a list, a set, or a path string"
        % type(result).__name__
    )


def _render_path(value: str) -> str:
    """A returned string is a file reference, so it has to name a real file."""
    path = Path(value).expanduser()
    if not path.exists():
        raise OutputError(
            "run() returned the string %r, which must be a path to an "
            "existing file or directory" % value
        )
    return value


def _render_element(item: Any, as_json: bool) -> str:
    if isinstance(item, str) and not as_json:
        return item
    return _dumps(item)


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=_json_default)
    except (TypeError, ValueError) as exc:
        raise OutputError("run() returned a value that is not JSON: %s" % exc)


def _json_default(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    if isinstance(value, Path):
        return str(value)
    raise TypeError("%s is not JSON serializable" % type(value).__name__)


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
