"""Emit random integers, one record each.

    $ pgm randint
    {"value": 37}
    ...100 lines in all

    $ pgm --count=3 --start=1 --end=6 randint
    {"value": 4}
    {"value": 1}
    {"value": 6}

Both ends of the range are included. Each call produces `count` records, and
pgm calls run() once per input record -- so this is normally the first stage in
a pipeline, where the single empty record makes it fire exactly once.
"""

import random

#: What the script emits when the command line says nothing.
DEFAULTS = {"count": 100, "start": 0, "end": 100}


def run(args: dict, data: dict) -> list:
    """Return `count` records, each holding one integer in [start, end]."""
    count = _integer("count", args)
    start = _integer("start", args)
    end = _integer("end", args)
    if count < 0:
        raise ValueError("count cannot be negative, got %d" % count)
    if start > end:
        raise ValueError("start %d is above end %d" % (start, end))
    return [{"value": random.randint(start, end)} for _ in range(count)]


def _integer(name: str, args: dict) -> int:
    """Read one option as an integer, falling back to its default.

    True is an int as far as Python is concerned, so a bare --count has to be
    turned away by hand: it means the user forgot the value, not that they
    wanted one record.
    """
    value = args.get(name, DEFAULTS[name])
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be a whole number, got %r" % (name, value))
    return value
