"""Show records as a table on stderr, for reading rather than piping.

    $ pgm --jql='project = ENG' --fields=key,summary,status,assignee jira |
      pgm --columns=key,summary,status,assignee list_print
    key    summary                    status  assignee
    -----  -------------------------  ------  -------------
    ENG-1  Ship the thing             Done    Ada Lovelace
    ENG-2  Ship the other thing       Open    -
    ENG-7  Work out what shipping...  Open    Grace Hopper
    list_print: 3 records

The table goes to stderr, which is where a pgm script talks to the person
running it, and nothing goes to stdout: this is a place to look, not a step to
pass through, and a screenful of JSON printed underneath the table it was made
into would be nobody's idea of easier to read. `--tee` hands the records on
unchanged for when it should be both.

Columns are every field the records have, in the order they were first seen,
each one as wide as the widest thing in it. --columns says which to show, and
in what order, which is the thing to reach for on records as wide as Jira's:
what is named is shown, and what is not is fitted to the terminal, with a note
about anything that did not fit.

Values are shown the way they read best rather than the way they serialize.
Text is put on one line, numbers line up on the right, a missing value or a null
is a `-`, and a nested object is shown by its name -- Jira's status arrives as
an object and reads as `Done`. --raw shows every value as the JSON it is.
--width sets how wide one column may get before its values are cut short.
"""

import json
import shutil
import sys
from typing import Any, List, Sequence

from pgm import get_int, get_str, log

#: Between one column and the next.
GAP = "  "

#: Under the headers, and how much of a column it underlines.
RULE = "-"

#: What stands in for a value a record has as null, or does not have at all. A
#: blank would leave a column looking like it ended early.
MISSING = "-"

#: How wide one column may get before its values are cut short, and what marks
#: one that was. Wide enough for a Jira summary to be worth reading, narrow
#: enough that one long field does not push everything else off the screen.
DEFAULT_WIDTH = 40
ELLIPSIS = "..."

#: A column has to be able to hold something plus the mark saying there was
#: more, or cutting it short says nothing at all.
MIN_WIDTH = len(ELLIPSIS) + 1

#: What a nested object is called, best name first. Jira sends a status, a
#: project and a person as objects, and every one of them is worth a word
#: rather than a line of JSON.
NAME_KEYS = ("displayName", "name", "value", "summary", "key", "id")

#: How wide to assume the terminal is when there is nothing to ask.
FALLBACK_TERMINAL_WIDTH = 80

#: What a number is, and what a number is not.
NUMBERS = (int, float)


def run_all(args: dict, records: list) -> List[dict]:
    """Print the records as a table, and hand back what was asked for."""
    onward = records if args.get("tee") else []
    if not records:
        log("no records to show")
        return onward

    raw = bool(args.get("raw"))
    width = _width(args)
    named = _named_columns(args)
    columns = named or _every_column(records)
    if not columns:
        # Records with no fields in them: there is nothing to put in a column,
        # and how many of them there were is the whole of what can be said.
        log("%s, with no fields to show" % _counted(records))
        return onward
    rows = [[_cell(record.get(name), raw) for name in columns] for record in records]

    table = _table(columns, rows, width)
    # Named columns are shown however wide they come to: they were asked for by
    # name, and quietly dropping one would answer a question with less than was
    # asked. The rest are fitted, because everything a Jira issue has is more
    # columns than any terminal has room for.
    shown = list(range(len(columns))) if named else _fitted(table)
    _show([table[index] for index in shown])
    log(_footer(records, _hidden(columns, shown)))
    return onward


def _table(columns: Sequence[str], rows: List[List[str]], width: int) -> List[dict]:
    """One dict per column: what it is called, how wide, and which way it sits.

    Built for every column even when only some will be shown, because how wide
    a column is decides whether the one after it fits.
    """
    table = []
    for index, name in enumerate(columns):
        cells = [row[index] for row in rows]
        size = min(width, max([len(name)] + [len(cell) for cell in cells]))
        table.append(
            {
                "cells": [_short(cell, size) for cell in cells],
                "head": _short(name, size),
                "right": _is_number_column(cells),
                "width": size,
            }
        )
    return table


def _show(columns: List[dict]) -> None:
    """Write the headers, a rule under them, and the rows.

    Straight to stderr rather than through log(), which tags every line it
    writes with the script's name: here that would be a tag down the side of a
    table, spending on saying where it came from the width the table wants for
    saying what is in it.
    """
    lines = [
        _line([column["head"] for column in columns], columns),
        _line([RULE * column["width"] for column in columns], columns),
    ]
    for index in range(len(columns[0]["cells"])):
        lines.append(_line([column["cells"][index] for column in columns], columns))
    sys.stderr.write("".join(line + "\n" for line in lines))
    sys.stderr.flush()


def _line(cells: Sequence[str], columns: Sequence[dict]) -> str:
    """One row, padded into its columns. Nothing trails off the right."""
    padded = [
        cell.rjust(column["width"]) if column["right"] else cell.ljust(column["width"])
        for cell, column in zip(cells, columns)
    ]
    return GAP.join(padded).rstrip()


def _fitted(table: List[dict]) -> List[int]:
    """Which columns the terminal has room for, in the order they came.

    A column too wide to fit is passed over rather than taken as the end of the
    table: one long field early on -- a Jira summary, most of the time -- would
    otherwise hide every short one behind it, and four narrow columns say more
    than one wide one does.

    The first column is kept whatever it costs. A table of no columns is not a
    narrower answer to the question, it is no answer.
    """
    room = _terminal_width()
    used = 0
    shown = []  # type: List[int]
    for index, column in enumerate(table):
        needed = column["width"] + (len(GAP) if shown else 0)
        if shown and used + needed > room:
            continue
        used += needed
        shown.append(index)
    return shown


def _hidden(columns: Sequence[str], shown: Sequence[int]) -> List[str]:
    """The columns that were left out, by name."""
    kept = set(shown)
    return [name for index, name in enumerate(columns) if index not in kept]


def _terminal_width() -> int:
    """How much room there is across, or a sensible guess at it."""
    try:
        return shutil.get_terminal_size((FALLBACK_TERMINAL_WIDTH, 0)).columns
    except (OSError, ValueError):
        return FALLBACK_TERMINAL_WIDTH


def _footer(records: list, hidden: Sequence[str]) -> str:
    """How much was shown, and what was not.

    A column left out is said outright, with the option that would bring it
    back: a table that quietly stops at the edge of the terminal is a table
    that lies about what came in.
    """
    if not hidden:
        return _counted(records)
    return "%s; %d more column%s not shown (%s) -- name them with --columns" % (
        _counted(records),
        len(hidden),
        "" if len(hidden) == 1 else "s",
        ", ".join(hidden),
    )


def _counted(records: list) -> str:
    """How many records there were, said in the singular when there was one."""
    return "%d record%s" % (len(records), "" if len(records) == 1 else "s")


def _every_column(records: list) -> List[str]:
    """Every field the records have, in the order they were first seen."""
    columns = []  # type: List[str]
    for record in records:
        for name in record:
            if name not in columns:
                columns.append(name)
    return columns


def _named_columns(args: dict) -> List[str]:
    """The columns that were asked for by name, if any were."""
    if "columns" not in args:
        return []
    named = [part.strip() for part in get_str(args, "columns").split(",")]
    columns = [part for part in named if part]
    if not columns:
        raise ValueError("--columns names no columns; leave it out to show them all")
    return columns


def _width(args: dict) -> int:
    """How wide one column may get."""
    width = get_int(args, "width", DEFAULT_WIDTH)
    if width < MIN_WIDTH:
        raise ValueError("--width must be at least %d, got %d" % (MIN_WIDTH, width))
    return width


def _is_number_column(cells: Sequence[str]) -> bool:
    """Whether a column is numbers, and so lines up on the right.

    Read off what was rendered rather than off the values, so that a column of
    numbers stays a column of numbers with a null or two in it, and --raw --
    where a number is still spelled the same -- lines up as well.
    """
    numbers = [cell for cell in cells if cell != MISSING]
    return bool(numbers) and all(_looks_numeric(cell) for cell in numbers)


def _looks_numeric(cell: str) -> bool:
    try:
        float(cell)
    except ValueError:
        return False
    return True


def _cell(value: Any, raw: bool) -> str:
    """One value, as the thing to read rather than the thing it serializes to."""
    if raw:
        return _compact(value)
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _one_line(value)
    if isinstance(value, NUMBERS):
        return str(value)
    if isinstance(value, dict):
        return _name_of(value)
    if isinstance(value, list):
        return ", ".join(_cell(item, raw) for item in value) or MISSING
    return _compact(value)


def _name_of(value: dict) -> str:
    """What to call a nested object: its name, if it has one it can be read by.

    Only a word or a number will do. An object whose name is another object has
    not been named, and showing the whole of it is the honest answer.
    """
    for key in NAME_KEYS:
        named = value.get(key)
        if isinstance(named, str) and named.strip():
            return _one_line(named)
        if isinstance(named, NUMBERS) and not isinstance(named, bool):
            return str(named)
    return _compact(value)


def _one_line(text: str) -> str:
    """Text with its line breaks and its runs of space taken out.

    A Jira description arrives with newlines in it, and one row of a table is
    one line: left as it came, a single record would take the table apart.
    """
    return " ".join(text.split()) or MISSING


def _compact(value: Any) -> str:
    """A value as the JSON it is, on one line."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        # Nothing off a pgm pipeline gets here -- it arrived as JSON -- but a
        # table is for looking at, and refusing to draw one is a poor answer to
        # a value that is merely strange.
        return str(value)


def _short(text: str, width: int) -> str:
    """Text cut down to the width of its column, saying that it was cut."""
    if len(text) <= width:
        return text
    return text[: width - len(ELLIPSIS)] + ELLIPSIS
