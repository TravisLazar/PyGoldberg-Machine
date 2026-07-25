"""What a script may want from pgm itself.

A script is handed two dicts and has to make sense of them, and it has no way
to talk to the person running it: stdout belongs to the pipeline. These cover
both, and they are the only things a script is expected to import.

    from pgm import get_int, log

The readers take any dict, so they work on ``data`` as readily as on ``args``.
"""

import sys
from typing import Any, Dict, NoReturn, Optional

from .errors import ArgumentError

#: Stands in for "no default", so that a missing option is an error rather
#: than a None the script has to notice.
_REQUIRED = object()

#: Which script pgm is running, so log() can say who is speaking. The runner
#: sets it; a script never has to.
_script_name = None  # type: Optional[str]


def set_script_name(name: Optional[str]) -> None:
    """Framework-internal: record the script log() is speaking for."""
    global _script_name
    _script_name = name


def script_name() -> Optional[str]:
    """Framework-internal: who log() is speaking for right now."""
    return _script_name


def log(*parts: Any) -> None:
    """Write one line to stderr, clear of the pipeline.

    stdout carries records and nothing else -- a stray print would land in the
    next script's input as unreadable junk -- so this is how a script says
    anything to the person running it.

        log("wrote", count, "rows to", path)

    Parts are joined with spaces and stringified, like print(). The line is
    tagged with the script's name, because in `pgm a | pgm b` both ends share
    one stderr.
    """
    message = " ".join(str(part) for part in parts)
    if _script_name:
        message = "%s: %s" % (_script_name, message)
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def get_int(args: Dict[str, Any], name: str, default: Any = _REQUIRED) -> int:
    """Read one option as a whole number."""
    value = _lookup(args, name, default)
    if value is not default and (isinstance(value, bool) or not isinstance(value, int)):
        _reject(name, value, "a whole number")
    return value


def get_float(args: Dict[str, Any], name: str, default: Any = _REQUIRED) -> float:
    """Read one option as a number, whole or not."""
    value = _lookup(args, name, default)
    if value is default:
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(name, value, "a number")
    return float(value)


def get_str(args: Dict[str, Any], name: str, default: Any = _REQUIRED) -> str:
    """Read one option as text."""
    value = _lookup(args, name, default)
    if value is not default and not isinstance(value, str):
        _reject(name, value, "text")
    return value


def _lookup(args: Dict[str, Any], name: str, default: Any) -> Any:
    """Find the option, or fall back to what the script asked for.

    A default is handed back untouched: it is the script's own value, and
    checking it would report a script's bug in the words of a user's mistake.
    """
    if name in args:
        return args[name]
    if default is _REQUIRED:
        raise ArgumentError("%s is required" % _spelling(name))
    return default


def _reject(name: str, value: Any, expected: str) -> NoReturn:
    raise ArgumentError("%s must be %s, got %r" % (_spelling(name), expected, value))


def _spelling(name: str) -> str:
    """Name the option the way it is written on the command line."""
    return "--%s" % name.replace("_", "-")
