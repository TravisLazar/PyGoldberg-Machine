"""Emit random integers, or add one to each record that arrives.

    $ pgm --count=3 --start=1 --end=6 randint
    {"value": 4}
    {"value": 1}
    {"value": 6}

Given records it fills a field on each of them instead, which is how two of
these make a table with a column apiece:

    $ pgm --count=3 --end=9 randint | pgm --key=other --end=99 randint
    {"other": 57, "value": 4}
    {"other": 12, "value": 1}
    {"other": 83, "value": 6}

Both ends of the range are included. --count is how many records to make out of
nothing; when records arrive there are already that many, so it is not needed,
and one that disagrees is an error rather than a guess at which was meant.
"""

import random

from pgm import get_int, get_str


def run_all(args: dict, records: list) -> list:
    """Make `count` records, or fill a field in on the records given."""
    key = get_str(args, "key", "value")
    start = get_int(args, "start", 0)
    end = get_int(args, "end", 100)

    if start > end:
        raise ValueError("start %d is above end %d" % (start, end))

    if not records:
        return [{key: random.randint(start, end)} for _ in range(_count(args))]

    _check_shape(args, records)
    return [_filled(record, key, start, end) for record in records]


def _count(args: dict) -> int:
    """How many records to make when there are none to fill in."""
    count = get_int(args, "count", 100)
    if count < 0:
        raise ValueError("count cannot be negative, got %d" % count)
    return count


def _check_shape(args: dict, records: list) -> None:
    """Records arrived, so how many there are is already settled.

    Saying --count as well is only worth answering when it agrees; when it does
    not, one of the two is a mistake and pgm cannot know which.
    """
    if "count" not in args:
        return
    count = get_int(args, "count")
    if count != len(records):
        raise ValueError(
            "invalid shape: --count=%d but %d records arrived; leave --count "
            "out to fill in the records that came" % (count, len(records))
        )


def _filled(record: dict, key: str, start: int, end: int) -> dict:
    """A copy of the record with one more field in it.

    A field that is already there is left alone and complained about: chaining
    two of these without a second --key would otherwise throw the first set of
    numbers away without a word.
    """
    if key in record:
        raise ValueError(
            "a record already has %r in it; give --key another name rather "
            "than writing over it" % key
        )
    return dict(record, **{key: random.randint(start, end)})
