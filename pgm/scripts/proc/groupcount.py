"""Count how many records fall into each group.

    $ echo '[{"c": "red"}, {"c": "blue"}, {"c": "red"}]' | pgm --groupname=c groupcount
    {"c": "red", "count": 2}
    {"c": "blue", "count": 1}

Which is what a histogram is made of, one bar per group:

    $ pgm --count=200 --end=4 randint | pgm --groupname=value groupcount
    {"count": 33, "value": 0}
    {"count": 36, "value": 1}
    ...

--groupname says which field to gather records under, and is required: there
is no field a script could sensibly guess at. The group keeps its own name in
the output, so what comes out says what it was grouped by. Groups come out in
the order they were first seen, so a sorted input charts as a sorted histogram.
"""

from pgm import get_str

#: Where the tally goes, which is why a group cannot also be named that.
COUNT_KEY = "count"

#: What can name a group. A list or a dict has no identity to gather under.
GROUPABLE = (str, int, float, bool, type(None))


def run_all(args: dict, records: list) -> list:
    """Gather records by one field, and count each gathering."""
    groupname = get_str(args, "groupname")
    if groupname == COUNT_KEY:
        raise ValueError(
            "--groupname=%s collides with the field the tally goes in" % COUNT_KEY
        )

    groups = {}
    for record in records:
        value = _group_of(record, groupname)
        # Keyed by type as well as value, so that True and 1 stay two groups.
        key = (type(value).__name__, value)
        if key not in groups:
            groups[key] = {groupname: value, COUNT_KEY: 0}
        groups[key][COUNT_KEY] += 1
    return list(groups.values())


def _group_of(record: dict, groupname: str):
    """The value a record is gathered under, or why it cannot be."""
    if groupname not in record:
        raise ValueError(
            "a record has no %r to group by; it has %s"
            % (groupname, ", ".join(sorted(record)) or "no fields at all")
        )
    value = record[groupname]
    if not isinstance(value, GROUPABLE):
        raise ValueError(
            "%r is %s in a record, which cannot name a group"
            % (groupname, type(value).__name__)
        )
    return value
