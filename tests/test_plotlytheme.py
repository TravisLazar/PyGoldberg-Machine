import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def theme():
    return load_module(next(discovery.bundled_scripts_dir().rglob("plotlytheme.py")))


def figure(*traces, **layout):
    return {"data": list(traces) or [bar()], "layout": layout}


def bar(**overrides):
    return dict({"type": "bar", "x": ["a", "b"], "y": [2, 1]}, **overrides)


def themed(theme, fig, **args):
    return theme.run(args, fig)


# What was plotted is not the theme's business.


def test_the_data_comes_back_saying_the_same_thing(theme):
    fig = figure(bar(), {"type": "bar", "x": ["c"], "y": [9]})

    out = themed(theme, fig)

    for before, after in zip(fig["data"], out["data"]):
        for key in ("type", "x", "y"):
            assert after[key] == before[key]


def test_the_figure_is_still_a_figure_plotly_will_draw(theme, tmp_path):
    import plotly.io as pio

    pio.write_image(themed(theme, figure(title={"text": "Rolls"})),
                    str(tmp_path / "chart.png"), format="png")

    assert (tmp_path / "chart.png").read_bytes().startswith(b"\x89PNG\r\n")


def test_the_bars_stand_on_the_baseline(theme):
    # This one pays for a browser, because it is about where things landed
    # rather than what was asked for. plotly's margin padding puts the axis
    # line a few pixels below the plot area, which leaves every bar hovering
    # over its own baseline; nothing but the drawing says whether it is gone.
    import re

    import plotly.io as pio

    def found(pattern, svg):
        return float(re.search(pattern, svg).group(1))

    svg = pio.to_image(themed(theme, figure()), format="svg").decode()
    plot_top = found(r'class="xy" transform="translate\([\d.]+,([\d.]+)\)', svg)
    foot = found(r'class="point"><path d="M[\d.]+,([\d.]+)', svg)
    baseline = found(r'class="xlines-above crisp" d="M[\d.]+,([\d.]+)H', svg)

    assert abs(baseline - (plot_top + foot)) <= 1  # a 1px rule, drawn on the foot


def test_anything_else_in_the_figure_is_carried_through(theme):
    out = theme.run({}, dict(figure(), frames=[], config={"staticPlot": True}))

    assert out["frames"] == []
    assert out["config"] == {"staticPlot": True}


# Styling goes underneath what the figure already said.


def test_what_the_figure_said_wins(theme):
    fig = figure(bar(marker={"color": "#ff0000", "cornerradius": 12}),
                 paper_bgcolor="#000000",
                 xaxis={"type": "category", "showgrid": True})

    out = themed(theme, fig)

    assert out["data"][0]["marker"]["color"] == "#ff0000"
    assert out["data"][0]["marker"]["cornerradius"] == 12
    assert out["layout"]["paper_bgcolor"] == "#000000"
    assert out["layout"]["xaxis"]["showgrid"] is True


def test_what_the_figure_left_unsaid_is_filled_in(theme):
    fig = figure(bar(marker={"color": "#ff0000"}))

    out = themed(theme, fig)

    assert out["data"][0]["marker"]["line"]["width"] == 0
    assert out["layout"]["plot_bgcolor"] == "#fcfcfb"
    assert out["layout"]["font"]["size"] == theme.BODY_SIZE


def test_running_it_twice_changes_nothing_the_second_time(theme):
    once = themed(theme, figure(title={"text": "Rolls"}))

    assert themed(theme, once) == once


def test_a_title_written_as_a_bare_string_still_gets_its_font(theme):
    # plotly takes both spellings; only one of them has room for a font.
    out = themed(theme, figure(title="Rolls", xaxis={"title": "bucket"}))

    assert out["layout"]["title"]["text"] == "Rolls"
    assert out["layout"]["title"]["font"]["size"] == theme.TITLE_SIZE
    assert out["layout"]["xaxis"]["title"]["text"] == "bucket"
    assert out["layout"]["xaxis"]["title"]["font"]["color"] == "#52514e"


# The rules the theme is there to apply.


def test_the_series_colours_are_handed_out_in_order(theme):
    out = themed(theme, figure())

    assert out["layout"]["colorway"] == list(theme.SERIES["light"])


def test_dark_is_its_own_palette_not_light_turned_over(theme):
    light = themed(theme, figure())["layout"]
    dark = themed(theme, figure(), mode="dark")["layout"]

    assert dark["paper_bgcolor"] == "#1a1a19"
    assert dark["colorway"] != light["colorway"]
    assert dark["yaxis"]["gridcolor"] != light["yaxis"]["gridcolor"]


def test_the_grid_runs_one_way_only(theme):
    layout = themed(theme, figure())["layout"]

    assert layout["yaxis"]["showgrid"] is True
    assert layout["xaxis"]["showgrid"] is False
    assert layout["xaxis"]["showline"] is True  # a baseline to stand the bars on


def test_bars_that_run_across_swap_which_axis_is_which(theme):
    sideways = figure({"type": "bar", "orientation": "h", "y": ["a"], "x": [2]})

    layout = themed(theme, sideways)["layout"]

    assert layout["xaxis"]["showgrid"] is True
    assert layout["yaxis"]["showgrid"] is False


def test_a_bar_chart_reads_from_zero(theme):
    layout = themed(theme, figure())["layout"]

    assert layout["yaxis"]["rangemode"] == "tozero"


def test_a_line_chart_is_left_to_its_own_range(theme):
    line = figure({"type": "scatter", "x": [1, 2], "y": [90, 91]})

    assert "rangemode" not in themed(theme, line)["layout"]["yaxis"]


def test_lines_and_dots_get_their_own_marks(theme):
    line = figure({"type": "scatter", "x": [1, 2], "y": [1, 2]})

    trace = themed(theme, line)["data"][0]

    assert trace["line"]["width"] == theme.LINE_WIDTH
    assert trace["marker"]["size"] == theme.MARKER_SIZE
    assert trace["marker"]["line"] == {"width": theme.RING_WIDTH, "color": "#fcfcfb"}


def test_a_trace_the_theme_has_no_opinion_about_is_left_alone(theme):
    pie = {"type": "pie", "labels": ["a"], "values": [1]}

    assert themed(theme, figure(pie))["data"][0] == pie


# One series has nothing to tell apart.


def test_one_series_gets_no_legend(theme):
    assert themed(theme, figure())["layout"]["showlegend"] is False


def test_two_series_get_one(theme):
    out = themed(theme, figure(bar(), bar()))

    assert out["layout"]["showlegend"] is True
    assert out["layout"]["legend"]["orientation"] == "h"


# Bars are capped, and so is the air around them.


def test_bars_are_capped_rather_than_filling_their_slot(theme):
    twenty = [str(n) for n in range(20)]
    layout = themed(theme, figure(bar(x=twenty, y=[1] * 20)))["layout"]
    across = layout["width"] - layout["margin"]["l"] - layout["margin"]["r"]

    drawn = across / 20 * (1 - layout["bargap"])

    assert drawn == pytest.approx(theme.MAX_BAR_PX, abs=1)


def test_but_a_few_bars_are_not_left_stranded_by_the_cap(theme):
    # Three 24px bars in an 800px chart would be washing on a line, so the
    # emptiness is capped too and the bars are allowed to be wider.
    layout = themed(theme, figure(bar(x=list("abc"), y=[1, 2, 3])))["layout"]
    across = layout["width"] - layout["margin"]["l"] - layout["margin"]["r"]

    assert layout["bargap"] == theme.MAX_BARGAP
    assert across / 3 * (1 - layout["bargap"]) > theme.MAX_BAR_PX


def test_many_bars_still_keep_air_between_them(theme):
    many = [str(n) for n in range(200)]
    layout = themed(theme, figure(bar(x=many, y=[1] * 200)))["layout"]

    assert layout["bargap"] >= theme.MIN_BARGAP


def test_the_cap_counts_bars_grouped_in_one_slot(theme):
    one = themed(theme, figure(bar()))["layout"]["bargap"]
    three = themed(theme, figure(bar(), bar(), bar()))["layout"]["bargap"]

    assert three >= one


# Room is made for what the chart actually has.


def test_a_bare_chart_keeps_a_snug_margin(theme):
    assert themed(theme, figure())["layout"]["margin"]["t"] == theme.MARGIN["t"]


def test_a_title_a_subtitle_and_a_legend_are_each_paid_for(theme):
    title = {"text": "Rolls", "subtitle": {"text": "per bucket"}}

    top = themed(theme, figure(bar(), bar(), title=title))["layout"]["margin"]["t"]

    assert top == (
        theme.MARGIN["t"] + theme.TITLE_ROOM + theme.SUBTITLE_ROOM + theme.LEGEND_ROOM
    )


def test_an_empty_title_is_not_a_title(theme):
    assert themed(theme, figure(title={"text": ""}))["layout"]["margin"]["t"] == (
        theme.MARGIN["t"]
    )


# What it refuses.


def test_a_record_that_is_not_a_figure_is_reported(theme):
    with pytest.raises(ValueError) as excinfo:
        theme.run({}, {"value": 3})
    message = str(excinfo.value)
    assert "not a plotly figure" in message
    assert "value" in message


def test_data_that_is_not_traces_is_reported(theme):
    for data in ("bar", [1, 2], {"type": "bar"}):
        with pytest.raises(ValueError) as excinfo:
            theme.run({}, {"data": data})
        assert "list of traces" in str(excinfo.value)


def test_a_layout_that_is_not_an_object_is_reported(theme):
    with pytest.raises(ValueError) as excinfo:
        theme.run({}, {"data": [bar()], "layout": "modern"})
    assert "'layout' must be an object" in str(excinfo.value)


def test_more_series_than_colour_can_carry_is_reported(theme):
    with pytest.raises(ValueError) as excinfo:
        theme.run({}, figure(*[bar() for _ in range(9)]))
    message = str(excinfo.value)
    assert "9 traces is more than colour can tell apart" in message
    assert "draw several charts" in message


def test_the_last_slot_is_still_allowed(theme):
    out = themed(theme, figure(*[bar() for _ in range(8)]))

    assert len(out["data"]) == 8


def test_a_mode_that_is_neither_is_refused(theme):
    with pytest.raises(ValueError) as excinfo:
        theme.run({"mode": "sepia"}, figure())
    assert "--mode must be dark or light, got 'sepia'" in str(excinfo.value)


def test_the_mode_may_be_written_in_any_case(theme):
    layout = themed(theme, figure(), mode=" DARK ")["layout"]

    assert layout["paper_bgcolor"] == "#1a1a19"


def test_a_mode_that_is_not_text_is_refused(theme):
    with pytest.raises(ArgumentError) as excinfo:
        theme.run({"mode": True}, figure())
    assert "--mode must be text" in str(excinfo.value)
