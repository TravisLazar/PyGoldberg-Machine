"""Running one script from inside another.

A pipeline is scripts feeding each other records, and there is no reason that
has to go through a shell. call() runs another script here and now and hands
back what it produced:

    from pgm import call

    def run(args: dict, data: dict) -> list:
        numbers = call("randint", count=3, end=9)
        return call("double", numbers, factor=1.5)

which is `pgm --count=3 --end=9 randint | pgm --factor=1.5 double`, and means
it literally: the records go out through the same rendering a pipe would use
and come back through the same parsing. So a script behaves the same whether it
was called or piped, and there is only one set of rules to learn.
"""

from typing import Any, List, Optional

from . import helpers
from .discovery import find_script
from .errors import InvalidScriptError
from .runner import run_script
from .streams import read_records

#: How deep scripts may call each other before pgm assumes a loop, in the
#: spirit of the hop limit on input that resolves to another file.
MAX_CALL_DEPTH = 10

#: The scripts currently on the stack, oldest first.
_running = []  # type: List[str]


def call(script: str, data: Any = None, /, **options: Any) -> List[dict]:
    """Run another script and return the records it produced.

    `script` is a name, resolved exactly as the command line resolves one.
    `data` is what it should see: nothing, one record, or a list of them --
    and, as on the command line, it is called once per record. Options are
    keywords, so call("randint", count=3) is `pgm --count=3 randint`.

    The answer is always a list of records, however the other script phrased
    its return: a dict is one record, a list is flattened, and a returned path
    is read back off disk the way the next script in a pipe would read it.
    Index [0] when you know there is exactly one.
    """
    path = find_script(script)
    _guard(path.stem)
    records = _as_records(data)

    # run_script speaks for the callee while it runs, so log() lines carry the
    # right name; the caller gets its own name back afterwards.
    speaking_for = helpers.script_name()
    _running.append(path.stem)
    try:
        lines = run_script(path, options, records)
    finally:
        _running.pop()
        helpers.set_script_name(speaking_for)

    return read_records("\n".join(lines))


def _guard(name: str) -> None:
    """Stop a script that calls a script that calls a script that..."""
    if len(_running) >= MAX_CALL_DEPTH:
        raise InvalidScriptError(
            "scripts called each other %d deep (%s); this looks like a loop"
            % (MAX_CALL_DEPTH, " -> ".join(_running + [name]))
        )


def _as_records(data: Any) -> Optional[List[dict]]:
    """Turn what the caller passed into the records the script will see.

    Passing nothing stays None all the way to the runner, which is what tells
    it apart from a list of no records: call("total", []) has zero records to
    add up, while call("randint") was simply not given any.
    """
    if data is None:
        return None
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                raise TypeError(
                    "call() was given a list holding %s; every record has to "
                    "be a dict" % type(item).__name__
                )
        return data
    raise TypeError(
        "call() takes one record, a list of records, or nothing; got %s"
        % type(data).__name__
    )
