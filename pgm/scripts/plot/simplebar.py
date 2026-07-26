"""Plot records as a bar chart, one bar per category.

    $ pgm --count=300 --end=4 randint |
      pgm --groupname=value groupcount |
      pgm --sortkeys=value sortlist |
      pgm --x=value --y=count --title=Rolls simplebar
    simplebar: wrote 5 bars to /tmp/pgm-simplebar-6b1f2a.png
    {"chart": "/tmp/pgm-simplebar-6b1f2a.png"}

The chart is drawn as a PNG, or as an SVG with --format=svg. It goes to a file,
and the record says where. It is not returned as a bare path, because a bare
path in pgm means "the data, over there" and the next script would read it: a
chart is something to look at, not more records. Pass --out to say where it
should go; without one it goes somewhere temporary rather than landing on top
of something in the working directory.

The figure is built as a plain dict rather than out of plotly objects, because
here a chart is data like everything else: what goes to plotly is the same kind
of thing that came in off the pipe, and can be read, logged, or written out.
"""

import os
import tempfile

import plotly.io as pio

from pgm import get_str, log

#: Where the written chart is reported.
CHART_KEY = "chart"

#: What a chart can be drawn as, and what it is drawn as when nobody says.
FORMATS = ("png", "svg")
DEFAULT_FORMAT = "png"

#: A bar's height has to be a number. Its category can be a word or a number,
#: but not a null, a list, or a dict -- those name nothing to stand a bar on.
HEIGHTS = (int, float)
CATEGORIES = (str, int, float)


def build_figure(args: dict, records: list) -> dict:
    """The plotly figure for these records, as a plain dict."""
    xkey = get_str(args, "x")
    ykey = get_str(args, "y")
    if not records:
        raise ValueError("there is nothing to plot")

    return {
        "data": [
            {
                "type": "bar",
                "x": [_category(record, xkey) for record in records],
                "y": [_height(record, ykey) for record in records],
            }
        ],
        "layout": {
            "title": {"text": get_str(args, "title", "", cast_numbers=True)},
            # Said outright, so that numeric categories stay one bar each
            # instead of turning the bottom of the chart into a number line.
            "xaxis": {"type": "category", "title": {"text": xkey}},
            "yaxis": {"title": {"text": ykey}},
        },
    }


def run_all(args: dict, records: list) -> dict:
    """Write a bar chart of the records, and say where it went."""
    figure = build_figure(args, records)
    out = get_str(args, "out", "")
    drawn_as = _format(args, out)
    path = out or _somewhere_temporary(drawn_as)
    pio.write_image(figure, path, format=drawn_as)
    log("wrote", len(records), "bars to", path)
    return {CHART_KEY: path}


def _format(args: dict, out: str) -> str:
    """Which of the two ways to draw it: said outright, or read off the name.

    A name that ends in .svg is asking for an SVG, so it gets one -- but only
    when nothing said otherwise. Being told both, and told two different
    things, is a question rather than something to pick a winner of.
    """
    asked = get_str(args, "format", "").strip().lower()
    if asked and asked not in FORMATS:
        raise ValueError(
            "--format must be %s, got %r" % (" or ".join(FORMATS), asked)
        )
    suffix = os.path.splitext(out)[1].lstrip(".").lower()
    named = suffix if suffix in FORMATS else ""
    if asked and named and asked != named:
        raise ValueError(
            "--format=%s does not match --out=%s; the file would not be what "
            "it says it is" % (asked, out)
        )
    return asked or named or DEFAULT_FORMAT


def _somewhere_temporary(drawn_as: str) -> str:
    """A new file out of the way, so nothing already there is written over."""
    handle, path = tempfile.mkstemp(prefix="pgm-simplebar-", suffix="." + drawn_as)
    os.close(handle)
    return path


def _category(record: dict, key: str):
    value = _field(record, key)
    if isinstance(value, bool) or not isinstance(value, CATEGORIES):
        raise ValueError(
            "%r is %s in a record, which cannot name a bar" % (key, _name_of(value))
        )
    return value


def _height(record: dict, key: str):
    value = _field(record, key)
    if isinstance(value, bool) or not isinstance(value, HEIGHTS):
        raise ValueError(
            "%r is %s in a record; a bar needs a number for its height"
            % (key, _name_of(value))
        )
    return value


def _field(record: dict, key: str):
    if key not in record:
        raise ValueError(
            "a record has no %r to plot; it has %s"
            % (key, ", ".join(sorted(record)) or "no fields at all")
        )
    return record[key]


def _name_of(value) -> str:
    return "null" if value is None else type(value).__name__
