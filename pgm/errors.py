"""Exceptions raised by pgm.

Every error surfaced to the user is a PgmError so the CLI can render a single
clean message on stderr instead of a traceback.
"""


class PgmError(Exception):
    """Base class for all pgm failures."""


class ScriptNotFoundError(PgmError):
    """No script with the requested name exists on any search path."""


class InvalidScriptError(PgmError):
    """A script file was found but does not satisfy the pgm contract."""


class ArgumentError(PgmError):
    """An option was wrong: the shape of the command line, or an option's type.

    Both are the same thing to the person at the keyboard, so both print as one
    plain line rather than as a script that blew up.
    """


class InputError(PgmError):
    """Data arriving on stdin could not be turned into records."""


class OutputError(PgmError):
    """A script returned something pgm does not know how to print."""
