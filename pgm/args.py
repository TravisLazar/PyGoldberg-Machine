"""Splitting a command line into pgm's own options and the script's args.

pgm has no declaration of what options a script takes, so it never puts itself
in a position to guess: every option carries its own value.

    --name=value        that value
    --name              True

One rule, and it makes the line position-independent. An option means the same
thing wherever it sits, values can never be mistaken for anything else, and the
only bare word left on the line is the name of the script to run.
"""

import json
from typing import Any, Dict, List, NoReturn, Optional, Tuple

from .errors import ArgumentError

#: pgm's own options: a closed set, none of which takes a value. They are
#: recognized wherever they appear and never reach the script. Every other
#: option on the line belongs to the script.
PGM_OPTIONS = frozenset(
    ["-h", "--help", "--list", "--where", "--paths", "--traceback", "--version"]
)


def _is_flag(token: str) -> bool:
    """True for anything written as an option, well-formed or not."""
    return token.startswith("-")


def split_argv(argv: List[str]) -> Tuple[List[str], Optional[str], List[str]]:
    """Split a command line into pgm's options, the script name, and the rest.

    pgm's own options come out first so they cannot be confused with a script's,
    and what remains sorts itself: a leading dash makes an option, and the one
    bare word is the script.
    """
    pgm_options = [token for token in argv if token in PGM_OPTIONS]
    rest = [token for token in argv if token not in PGM_OPTIONS]
    bare = [(index, token) for index, token in enumerate(rest) if not _is_flag(token)]
    if len(bare) > 1:
        _reject_extra_names(rest, bare)
    script = bare[0][1] if bare else None
    return pgm_options, script, [token for token in rest if _is_flag(token)]


def _reject_extra_names(rest: List[str], bare: List[Tuple[int, str]]) -> NoReturn:
    """Refuse a line with two script names on it.

    Almost always this is a value written with a space, so if a bare word is
    sitting right after an option, say so in the words the user typed.
    """
    names = ", ".join(repr(token) for _, token in bare)
    for index, token in bare:
        previous = rest[index - 1] if index else ""
        if _is_flag(previous) and "=" not in previous:
            raise ArgumentError(
                "more than one script name on the line (%s); a value needs an "
                "'=' -- did you mean %s=%s?" % (names, previous, token)
            )
    raise ArgumentError(
        "more than one script name on the line (%s); pgm runs one script at a "
        "time" % names
    )


def parse_script_args(tokens: List[str]) -> Dict[str, Any]:
    """Turn the tokens pgm did not need into the args dict a script receives."""
    args = {}  # type: Dict[str, Any]
    for token in tokens:
        if not _is_flag(token):
            raise ArgumentError(
                "unexpected argument %r; pgm takes one script name plus "
                "options for it" % token
            )
        name, equals, inline = token.partition("=")
        if name in PGM_OPTIONS:
            # split_argv already took the bare spelling, so getting here means
            # something like --traceback=true: pgm's option, given a value it
            # does not take. Handing it to the script would leave the user
            # wondering why pgm ignored it.
            raise ArgumentError("%s is pgm's own option and takes no value" % name)
        key = _key(name, token)
        if key in args:
            raise ArgumentError(
                "%s was given more than once; pass every value at once as "
                "%s='[...]' instead" % (name, name)
            )
        args[key] = _decode(inline) if equals else True
    return args


def _key(name: str, token: str) -> str:
    """--log-path becomes log_path, so a script can read args["log_path"].

    The name has to look like a name. Without that check `--offset -3` would
    quietly parse as two switches instead of telling the user to write
    `--offset=-3`.
    """
    key = name.lstrip("-").replace("-", "_")
    if not key or not (key[0].isalpha() or key[0] == "_"):
        raise ArgumentError(
            "%r is not an option name; write --name or --name=value" % token
        )
    return key


def _decode(text: str) -> Any:
    """A value that is valid JSON arrives as JSON; anything else is a string.

    So --verbosity=3 is a number and --logpath=out.txt is a string, without
    pgm having to be told which is which. It also means a script's args hold
    only the types its data holds.
    """
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except ValueError:
        return text


def _reject_constant(name: str) -> Any:
    # NaN and Infinity are accepted by Python's JSON parser but are not JSON,
    # and args carry only what pgm would be willing to print. Failing here
    # sends the token back as the string it arrived as.
    raise ValueError("%s is not JSON" % name)
