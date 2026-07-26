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

from pgm import get_int, get_str


def run(args: dict, data: dict) -> list:
    """Return `count` records, each holding one integer in [start, end]."""
    count = get_int(args, "count", 100)
    start = get_int(args, "start", 0)
    end = get_int(args, "end", 100)
    key = get_str(args, "key", "value")

    if count < 0:
        raise ValueError("count cannot be negative, got %d" % count)
    if start > end:
        raise ValueError("start %d is above end %d" % (start, end))
    
    return [{key: random.randint(start, end)} for _ in range(count)]
