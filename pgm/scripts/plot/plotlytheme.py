"""Restyle a whole plotly figure: modern, compact, and quiet about itself.

    $ echo /tmp/figure.json | pgm --mode=dark plotlytheme
    {"data": [...], "layout": {...}}

One record in, one record out, and the record is a plotly figure -- the same
{"data": [...], "layout": {...}} dict that goes to plotly. Nothing about what
is being plotted changes: the numbers, the categories, the order, the titles
and the chart type all come back exactly as they went in. What changes is
everything nobody was asked to decide -- the surface, the greys, the type, the
gaps, how fat a bar is allowed to get.

Style is offered *beneath* what the figure already says, never on top of it. A
figure that named its own colour, or set its own margins, keeps them; the theme
only fills in what was left unsaid. So it can be run on anything, including a
figure that has already been through it, and it is never an argument with the
script that built the chart.

The rules it applies are the boring, defensible ones:

  * one accessible categorical palette, handed out in a fixed order -- the
    order is what keeps neighbouring series apart for a colourblind reader,
    so it is never shuffled and never recycled past its eight slots
  * light and dark are both chosen, not one flipped into the other
  * horizontal gridlines only, hairline, in a grey one step off the surface;
    a baseline under the categories and no box around the plot
  * bars capped at 24 pixels, rounded at the data end, with real air between
  * value axes that start at zero, so a bar's length means its value
  * text in greys, never in a series colour; no legend for a single series,
    because the title already says what is being plotted
  * margins computed from what the chart actually has -- a title, a legend,
    axis labels -- so the spacing stays generous without going slack

Three of the light-mode series colours sit below 3:1 against the surface, which
is why the value axis keeps its labelled ticks: the numbers are readable from
the axis whatever the fill is doing.
"""

from pgm import get_str

#: The series colours, in the order they are handed out. Both columns are
#: chosen for the surface they sit on -- dark is its own set of steps rather
#: than light inverted -- and the ordering is a colourblind-safety mechanism
#: rather than a matter of taste: it was picked so that adjacent slots stay
#: apart under simulated colour vision deficiency. Past eight series, colour
#: has stopped telling anybody anything, so pgm does not invent a ninth.
SERIES = {
    "light": (
        "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
        "#e87ba4", "#008300", "#4a3aa7", "#e34948",
    ),
    "dark": (
        "#3987e5", "#d95926", "#199e70", "#c98500",
        "#d55181", "#008300", "#9085e9", "#e66767",
    ),
}

#: Everything that is not data: the surface the chart sits on, and the greys
#: the writing and the ruling are done in.
INK = {
    "light": {
        "surface": "#fcfcfb",
        "primary": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
    },
    "dark": {
        "surface": "#1a1a19",
        "primary": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
    },
}

#: Which surface the chart is being drawn for, and which one when nobody says.
MODES = tuple(sorted(SERIES))
DEFAULT_MODE = "light"

#: One face for the whole chart, including the numbers. A display or serif
#: face in a chart reads as decoration that wandered in from somewhere else.
FONT = "Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"

#: Type sizes. The title is the only thing allowed to be bigger than the body,
#: and only just: a chart is read by looking at the marks, not the words.
TITLE_SIZE = 17
TITLE_WEIGHT = 600
BODY_SIZE = 13
LABEL_SIZE = 12

#: How the marks are drawn. A bar wider than this stops reading as a
#: measurement and starts reading as a block of colour, so slots are given
#: extra air rather than letting the bars grow into them.
MAX_BAR_PX = 24
CORNER_RADIUS = 4
LINE_WIDTH = 2
MARKER_SIZE = 8
#: Dots carry a ring in the surface colour so they stay separate where they
#: cross a line or each other. White does the separating, never a border.
RING_WIDTH = 2

#: How much of each slot may be left empty, whatever the arithmetic says.
#: Bars that touch make the eye do the separating, and a gap does it for
#: free -- but a bar held to 24 pixels in a slot four times that is stranded
#: in the air it was given, so the emptiness is capped as well as the bar.
#: The two caps meet at about a dozen bars, and each governs its own side.
MIN_BARGAP = 0.3
MAX_BARGAP = 0.55
BARGROUPGAP = 0.08

#: The size a chart is drawn at when the figure does not say, and the room
#: kept around it. The margins are snug because the axes are told to claim
#: more if their own labels need it.
#:
#: The padding is nought on purpose. plotly's margin padding is not space
#: around the labels, it is space between the plot area and the axis line --
#: which lifts the line off the bottom of the chart and leaves every bar
#: floating a few pixels above the baseline it is supposed to be standing on.
#: The labels get their air from the standoff below instead, which moves the
#: writing without moving the line.
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 460
MARGIN = {"l": 56, "r": 24, "t": 24, "b": 44, "pad": 0}

#: How far the tick labels sit off their axis.
TICK_STANDOFF = 6

#: What each thing that lives above the plot costs in top margin. They stack
#: in this order -- title, subtitle, legend -- and the margin is the sum of
#: the ones this chart actually has.
TITLE_ROOM = 40
SUBTITLE_ROOM = 22
LEGEND_ROOM = 32

#: How far down from the top of the image the title starts. Pinned there
#: rather than centred in whatever margin it was given, so that the subtitle
#: below it grows downwards into space that was counted, instead of into the
#: legend.
TITLE_PAD = 20

#: Colour has run out of ways to say "a different one" past this many.
MAX_SERIES = len(SERIES[DEFAULT_MODE])

#: The two axes the theme dresses. A figure with a second y-axis is not one
#: this script has an opinion about -- it is a chart with a problem.
AXES = ("xaxis", "yaxis")


def run(args: dict, data: dict) -> dict:
    """Hand back the same figure, themed."""
    mode = _mode(args)
    figure = _figure(data)
    traces = figure["data"]
    layout = _spelled_out(figure.get("layout") or {})
    return dict(
        figure,
        data=[_beneath(trace, _mark(trace, mode)) for trace in traces],
        layout=_beneath(layout, _layout(mode, layout, traces)),
    )


def _layout(mode: str, layout: dict, traces: list) -> dict:
    """The styling offered for everything around the marks."""
    ink = INK[mode]
    title = layout.get("title")
    titled = bool(_title_text(title))
    subtitled = titled and bool(_title_text(_dict(title).get("subtitle")))
    legend = len(traces) > 1
    margin = _beneath(layout.get("margin") or {}, _margin(titled, subtitled, legend))
    width = layout.get("width") or DEFAULT_WIDTH
    height = layout.get("height") or DEFAULT_HEIGHT
    sideways = _sideways(traces)
    value, category = ("xaxis", "yaxis") if sideways else ("yaxis", "xaxis")
    return {
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "margin": margin,
        "paper_bgcolor": ink["surface"],
        "plot_bgcolor": ink["surface"],
        "colorway": list(SERIES[mode]),
        "font": {"family": FONT, "size": BODY_SIZE, "color": ink["secondary"]},
        "title": {
            "font": {
                "family": FONT,
                "size": TITLE_SIZE,
                "color": ink["primary"],
                "weight": TITLE_WEIGHT,
            },
            # Over the plot area rather than the whole image, so the title
            # lines up with the chart instead of floating left of it, and
            # pinned to the top so what hangs below it has somewhere to go.
            "xref": "paper",
            "x": 0,
            "xanchor": "left",
            "yref": "container",
            "y": 1,
            "yanchor": "top",
            "pad": {"t": TITLE_PAD},
            "subtitle": {
                "font": {"family": FONT, "size": BODY_SIZE, "color": ink["muted"]}
            },
        },
        # One series has nothing to tell apart from anything, and a box with a
        # single swatch in it just says the title again.
        "showlegend": legend,
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "title": {"text": ""},
            "font": {"family": FONT, "size": LABEL_SIZE, "color": ink["secondary"]},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "hoverlabel": {
            "bgcolor": ink["surface"],
            "bordercolor": ink["axis"],
            "font": {"family": FONT, "size": LABEL_SIZE, "color": ink["primary"]},
        },
        "barcornerradius": CORNER_RADIUS,
        "bargap": _bargap(traces, sideways, width, height, margin),
        "bargroupgap": BARGROUPGAP,
        value: _value_axis(ink, traces),
        category: _category_axis(ink),
    }


def _value_axis(ink: dict, traces: list) -> dict:
    """The axis the numbers are read off: ruled, unlined, and starting at zero.

    Gridlines run one way only. A grid in both directions is graph paper, and
    the reader has to find the chart in it.
    """
    axis = dict(
        _axis(ink),
        showgrid=True,
        gridcolor=ink["grid"],
        gridwidth=1,
        griddash="solid",
        showline=False,
        separatethousands=True,
    )
    if any(trace.get("type") == "bar" for trace in traces):
        # A bar means its length, which it only does from zero. An axis that
        # starts anywhere else draws a difference several times life size.
        axis["rangemode"] = "tozero"
    return axis


def _category_axis(ink: dict) -> dict:
    """The axis things are named along: a baseline to stand on, and no grid."""
    return dict(
        _axis(ink),
        showgrid=False,
        showline=True,
        linecolor=ink["axis"],
        linewidth=1,
    )


def _axis(ink: dict) -> dict:
    """What both axes wear: quiet writing, no tick marks, and room to breathe.

    automargin is how the margins get to stay snug: an axis whose labels do
    not fit asks for the room it needs rather than being given it in advance
    against the day a long one turns up.
    """
    return {
        "zeroline": False,
        "ticks": "",
        "ticklabelstandoff": TICK_STANDOFF,
        "tickfont": {"family": FONT, "size": LABEL_SIZE, "color": ink["muted"]},
        "title": {
            "font": {"family": FONT, "size": LABEL_SIZE, "color": ink["secondary"]}
        },
        "automargin": True,
    }


def _mark(trace: dict, mode: str) -> dict:
    """The styling offered for one trace, by what it is.

    Colour is not set here: the palette goes on the layout as a colorway, so a
    trace that named its own colour keeps it and the rest are handed slots in
    order -- which is what makes the order mean anything.
    """
    ink = INK[mode]
    kind = trace.get("type") or "scatter"
    if kind == "bar":
        # Rounded at the data end, square on the baseline, and no outline: a
        # stroke around a mark is ink that is not data.
        return {"marker": {"cornerradius": CORNER_RADIUS, "line": {"width": 0}}}
    if kind.startswith("scatter"):
        return {
            "line": {"width": LINE_WIDTH},
            "marker": {
                "size": MARKER_SIZE,
                "line": {"width": RING_WIDTH, "color": ink["surface"]},
            },
        }
    return {}


def _margin(titled: bool, subtitled: bool, legend: bool) -> dict:
    """Room around the chart, counted from what the chart actually has.

    A fixed margin is either wasteful or tight depending on the chart that
    lands in it. This one pays for a title, a subtitle and a legend when there
    is one, and leaves the axes to ask for more if their labels need it.
    """
    top = MARGIN["t"]
    top += TITLE_ROOM if titled else 0
    top += SUBTITLE_ROOM if subtitled else 0
    top += LEGEND_ROOM if legend else 0
    return dict(MARGIN, t=top)


def _bargap(traces: list, sideways: bool, width, height, margin: dict) -> float:
    """How much of each slot to leave empty, so no bar grows past 24 pixels.

    Which is arithmetic rather than a constant: the same 0.2 that looks right
    for twenty bars gives three of them the proportions of a fence. Work back
    from the width the plot area actually has, and cap the bar instead.
    """
    bars = [trace for trace in traces if trace.get("type") == "bar"]
    slots = max((len(_along(trace, sideways)) for trace in bars), default=0)
    if not slots:
        return MIN_BARGAP
    if sideways:
        across = height - margin.get("t", 0) - margin.get("b", 0)
    else:
        across = width - margin.get("l", 0) - margin.get("r", 0)
    per_slot = across / slots
    if per_slot <= 0:
        return MIN_BARGAP
    gap = 1 - (MAX_BAR_PX * len(bars)) / per_slot
    return round(min(max(gap, MIN_BARGAP), MAX_BARGAP), 3)


def _along(trace: dict, sideways: bool) -> list:
    """The values a trace has one bar of, whichever way it is pointing."""
    values = trace.get("y") if sideways else trace.get("x")
    if not isinstance(values, list):
        values = trace.get("x") if sideways else trace.get("y")
    return values if isinstance(values, list) else []


def _sideways(traces: list) -> bool:
    """Whether the bars run across, which swaps what each axis is for."""
    return any(
        trace.get("type") == "bar" and trace.get("orientation") == "h"
        for trace in traces
    )


def _beneath(said: dict, offered: dict) -> dict:
    """Merge the offered styling underneath what the figure already said.

    Every disagreement is settled the same way, all the way down: the figure
    wins. Theming a chart is filling in what nobody got round to, and a script
    that built a figure on purpose is not to be talked out of it here.
    """
    merged = dict(offered)
    for key, value in said.items():
        underneath = merged.get(key)
        if isinstance(value, dict) and isinstance(underneath, dict):
            merged[key] = _beneath(value, underneath)
        else:
            merged[key] = value
    return merged


def _spelled_out(layout: dict) -> dict:
    """Write a bare-string title out as the dict plotly also accepts.

    plotly takes {"title": "Sales"} and {"title": {"text": "Sales"}} alike, and
    real figures are written both ways. The theme has a font to put on it, and
    only one of those two has anywhere to put it.
    """
    spelled = dict(layout)
    if isinstance(spelled.get("title"), str):
        spelled["title"] = {"text": spelled["title"]}
    for name in AXES:
        axis = spelled.get(name)
        if isinstance(axis, dict) and isinstance(axis.get("title"), str):
            spelled[name] = dict(axis, title={"text": axis["title"]})
    return spelled


def _title_text(title) -> str:
    """What a title or a subtitle says, however it was written."""
    if isinstance(title, str):
        return title
    if isinstance(title, dict) and isinstance(title.get("text"), str):
        return title["text"]
    return ""


def _dict(value) -> dict:
    """Whatever was there, as something with keys to look in."""
    return value if isinstance(value, dict) else {}


def _mode(args: dict) -> str:
    """Which surface the chart is being drawn for."""
    mode = get_str(args, "mode", DEFAULT_MODE).strip().lower()
    if mode not in SERIES:
        raise ValueError("--mode must be %s, got %r" % (" or ".join(MODES), mode))
    return mode


def _figure(data: dict) -> dict:
    """Check that the record really is a figure before restyling it."""
    traces = data.get("data")
    if traces is None:
        raise ValueError(
            "this record is not a plotly figure: it has no 'data'. A figure is "
            '{"data": [...], "layout": {...}}, and this one has %s'
            % (", ".join(sorted(data)) or "no fields at all")
        )
    if not isinstance(traces, list) or not all(isinstance(t, dict) for t in traces):
        raise ValueError("a figure's 'data' must be a list of traces")
    if not isinstance(data.get("layout", {}), dict):
        raise ValueError("a figure's 'layout' must be an object")
    if len(traces) > MAX_SERIES:
        raise ValueError(
            "%d traces is more than colour can tell apart; there are %d series "
            "colours, and a ninth would say nothing. Group the tail together, "
            "or draw several charts" % (len(traces), MAX_SERIES)
        )
    return data
