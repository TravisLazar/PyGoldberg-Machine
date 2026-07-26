"""Put records in order, by one field or by several.

    $ echo '[{"n": 2}, {"n": 1}, {"n": 3}]' | pgm --sortkeys=n sortlist
    {"n": 1}
    {"n": 2}
    {"n": 3}

--sortkeys is required, and may name more than one field, separated by commas.
The second key settles the records the first one ties, the third settles what
the second ties, and so on:

    $ pgm --sortkeys=dept,surname,forename sortlist

--order is asc unless it is given as desc, and turns all of the keys around
together. Records that tie on every key keep the order they arrived in, so
sorting twice by different keys leaves the first sort showing through.
"""

from pgm import get_str

ASCENDING = "asc"
DESCENDING = "desc"

#: What can be put in order: numbers among numbers, and text among text.
#: Sorting a field that holds some of each has no answer worth inventing.
KINDS = {"numbers": (int, float, bool), "text": (str,)}


def run_all(args: dict, records: list) -> list:
    """Return the records in order, by each key in turn."""
    keys = _sortkeys(args)
    order = _order(args)
    for key in keys:
        _check_orderable(key, records)
    return sorted(
        records,
        key=lambda record: tuple(record[key] for key in keys),
        reverse=order == DESCENDING,
    )


def _sortkeys(args: dict) -> list:
    """The fields to sort by, in the order they were given."""
    given = get_str(args, "sortkeys")
    keys = [key.strip() for key in given.split(",")]
    if not all(keys):
        raise ValueError(
            "--sortkeys=%s has an empty key in it; name one field, or several "
            "separated by commas" % given
        )
    return keys


def _order(args: dict) -> str:
    order = get_str(args, "order", ASCENDING).strip().lower()
    if order not in (ASCENDING, DESCENDING):
        raise ValueError(
            "--order must be %s or %s, got %r" % (ASCENDING, DESCENDING, order)
        )
    return order


def _check_orderable(key: str, records: list) -> None:
    """Refuse a key the records cannot actually be put in order by.

    Sorting is where mixed types stop being a curiosity and start being a
    TypeError halfway through, so the complaint is made up front and says
    which field caused it.
    """
    kinds = set()
    for record in records:
        if key not in record:
            raise ValueError(
                "a record has no %r to sort by; it has %s"
                % (key, ", ".join(sorted(record)) or "no fields at all")
            )
        kinds.add(_kind_of(key, record[key]))
    if len(kinds) > 1:
        raise ValueError(
            "%r holds both %s, so the records cannot be put in order"
            % (key, " and ".join(sorted(kinds)))
        )


def _kind_of(key: str, value) -> str:
    for kind, types in KINDS.items():
        if isinstance(value, types):
            return kind
    raise ValueError(
        "%r is %s in a record, which cannot be put in order"
        % (key, "null" if value is None else type(value).__name__)
    )
