import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def simplebar():
    return load_module(next(discovery.bundled_scripts_dir().rglob("simplebar.py")))


@pytest.fixture
def axes():
    return {"x": "bucket", "y": "count"}


def bars(*pairs):
    return [{"bucket": bucket, "count": count} for bucket, count in pairs]


def trace(figure):
    return figure["data"][0]


@pytest.fixture
def drawn(simplebar, monkeypatch):
    """Record what would have been drawn, without starting a browser.

    Rendering really costs a second of Chrome, so only the two tests that
    check the actual bytes pay it; everything else about run_all -- which
    format, which file, what comes back -- is the same either way.
    """
    calls = []

    def write_image(figure, path, format):
        calls.append({"figure": figure, "path": str(path), "format": format})
        open(path, "w").close()

    monkeypatch.setattr(simplebar.pio, "write_image", write_image)
    return calls


def test_the_figure_is_a_plain_dict(simplebar, axes):
    figure = simplebar.build_figure(axes, bars(("a", 2), ("b", 1)))

    assert isinstance(figure, dict)
    assert figure["data"] == [{"type": "bar", "x": ["a", "b"], "y": [2, 1]}]


def test_records_are_plotted_in_the_order_they_arrived(simplebar, axes):
    figure = simplebar.build_figure(axes, bars(("c", 3), ("a", 1), ("b", 2)))

    assert trace(figure)["x"] == ["c", "a", "b"]
    assert trace(figure)["y"] == [3, 1, 2]


def test_the_axes_are_labelled_with_the_fields_they_came_from(simplebar, axes):
    layout = simplebar.build_figure(axes, bars(("a", 1)))["layout"]

    assert layout["xaxis"]["title"]["text"] == "bucket"
    assert layout["yaxis"]["title"]["text"] == "count"


def test_categories_stay_categories(simplebar, axes):
    # Numeric buckets are one bar each, not points on a number line.
    figure = simplebar.build_figure(axes, bars((10, 1), (20, 2)))

    assert figure["layout"]["xaxis"]["type"] == "category"
    assert trace(figure)["x"] == [10, 20]


def test_a_title_can_be_given(simplebar, axes):
    figure = simplebar.build_figure(dict(axes, title="Rolls"), bars(("a", 1)))

    assert figure["layout"]["title"]["text"] == "Rolls"


def test_a_numeric_title_is_still_a_title(simplebar, axes):
    figure = simplebar.build_figure(dict(axes, title=2024), bars(("a", 1)))

    assert figure["layout"]["title"]["text"] == "2024"


def test_no_title_asked_for_is_no_title(simplebar, axes):
    figure = simplebar.build_figure(axes, bars(("a", 1)))

    assert figure["layout"]["title"]["text"] == ""


def test_fractional_heights(simplebar, axes):
    figure = simplebar.build_figure(axes, bars(("a", 1.5)))

    assert trace(figure)["y"] == [1.5]


def test_both_axes_are_required(simplebar):
    with pytest.raises(ArgumentError) as excinfo:
        simplebar.build_figure({"y": "count"}, bars(("a", 1)))
    assert "--x is required" in str(excinfo.value)

    with pytest.raises(ArgumentError) as excinfo:
        simplebar.build_figure({"x": "bucket"}, bars(("a", 1)))
    assert "--y is required" in str(excinfo.value)


def test_there_has_to_be_something_to_plot(simplebar, axes):
    with pytest.raises(ValueError) as excinfo:
        simplebar.build_figure(axes, [])
    assert "nothing to plot" in str(excinfo.value)


def test_a_record_missing_a_field_is_reported(simplebar, axes):
    with pytest.raises(ValueError) as excinfo:
        simplebar.build_figure(axes, [{"count": 1, "other": 2}])
    message = str(excinfo.value)
    assert "no 'bucket' to plot" in message
    assert "count, other" in message


def test_a_height_that_is_not_a_number_is_reported(simplebar, axes):
    for height in ("tall", None, [1], True):
        with pytest.raises(ValueError) as excinfo:
            simplebar.build_figure(axes, bars(("a", height)))
        assert "needs a number for its height" in str(excinfo.value)


def test_a_category_that_cannot_name_a_bar_is_reported(simplebar, axes):
    for bucket in (None, [1], {"a": 1}, True):
        with pytest.raises(ValueError) as excinfo:
            simplebar.build_figure(axes, bars((bucket, 1)))
        assert "cannot name a bar" in str(excinfo.value)


def test_it_writes_where_it_was_told_and_says_so(simplebar, axes, tmp_path, drawn, capsys):
    out = tmp_path / "chart.png"

    written = simplebar.run_all(dict(axes, out=str(out)), bars(("a", 2), ("b", 1)))

    assert written == {"chart": str(out)}
    assert drawn[0]["path"] == str(out)
    assert out.is_file()
    assert "wrote 2 bars to" in capsys.readouterr().err


def test_what_goes_to_plotly_is_the_figure_that_was_built(simplebar, axes, tmp_path, drawn):
    records = bars(("a", 2), ("b", 1))

    simplebar.run_all(dict(axes, out=str(tmp_path / "chart.png")), records)

    assert drawn[0]["figure"] == simplebar.build_figure(axes, records)


def test_the_chart_is_reported_not_handed_on_as_data(simplebar, axes, tmp_path, drawn):
    # A bare path would have the next script read the image as records.
    from pgm.streams import render

    out = tmp_path / "chart.png"
    written = simplebar.run_all(dict(axes, out=str(out)), bars(("a", 1)))

    assert render(written) == ['{"chart": "%s"}' % out]


def test_png_unless_told_otherwise(simplebar, axes, tmp_path, drawn):
    simplebar.run_all(dict(axes, out=str(tmp_path / "chart.png")), bars(("a", 1)))

    assert drawn[0]["format"] == "png"


def test_the_format_can_be_asked_for(simplebar, axes, tmp_path, drawn):
    out = str(tmp_path / "chart.svg")

    simplebar.run_all(dict(axes, out=out, format="svg"), bars(("a", 1)))

    assert drawn[0]["format"] == "svg"


def test_the_format_can_be_read_off_the_file_name(simplebar, axes, tmp_path, drawn):
    simplebar.run_all(dict(axes, out=str(tmp_path / "chart.svg")), bars(("a", 1)))

    assert drawn[0]["format"] == "svg"


def test_a_name_that_says_nothing_still_gets_a_png(simplebar, axes, tmp_path, drawn):
    simplebar.run_all(dict(axes, out=str(tmp_path / "chart.bin")), bars(("a", 1)))

    assert drawn[0]["format"] == "png"


def test_the_format_may_be_written_in_any_case(simplebar, axes, tmp_path, drawn):
    simplebar.run_all(
        dict(axes, out=str(tmp_path / "chart.svg"), format="SVG"), bars(("a", 1))
    )

    assert drawn[0]["format"] == "svg"


def test_a_format_that_is_neither_is_refused(simplebar, axes, tmp_path):
    args = dict(axes, out=str(tmp_path / "c.pdf"), format="pdf")

    with pytest.raises(ValueError) as excinfo:
        simplebar.run_all(args, bars(("a", 1)))
    assert "--format must be png or svg, got 'pdf'" in str(excinfo.value)


def test_a_format_that_fights_the_file_name_is_refused(simplebar, axes, tmp_path):
    args = dict(axes, out=str(tmp_path / "chart.svg"), format="png")

    with pytest.raises(ValueError) as excinfo:
        simplebar.run_all(args, bars(("a", 1)))
    assert "would not be what it says it is" in str(excinfo.value)


def test_without_an_out_it_goes_somewhere_temporary(simplebar, axes, tmp_path, drawn):
    from pathlib import Path

    written = Path(simplebar.run_all(axes, bars(("a", 1)))["chart"])
    try:
        assert written.is_file()
        assert written.name.startswith("pgm-simplebar-")
        assert written.suffix == ".png"
        assert tmp_path not in written.parents
    finally:
        written.unlink()


def test_a_temporary_svg_is_named_like_one(simplebar, axes, drawn):
    from pathlib import Path

    written = Path(simplebar.run_all(dict(axes, format="svg"), bars(("a", 1)))["chart"])
    try:
        assert written.suffix == ".svg"
        assert drawn[0]["format"] == "svg"
    finally:
        written.unlink()


def test_plotly_still_checks_the_figure(simplebar, axes, tmp_path):
    # The dict is not a way around plotly's own validation.
    import plotly.io as pio

    with pytest.raises(ValueError):
        pio.write_image(
            {"data": [{"type": "bar", "nonsense": 1}]},
            str(tmp_path / "bad.png"),
            format="png",
        )


# The two that pay for a browser: everything above says what should be drawn,
# and these two prove that what lands on disk really is a PNG and an SVG.


def test_a_real_png_comes_out(simplebar, axes, tmp_path):
    out = tmp_path / "chart.png"

    simplebar.run_all(dict(axes, out=str(out), title="Rolls"), bars(("alpha", 7)))

    assert out.read_bytes().startswith(b"\x89PNG\r\n")


def test_a_real_svg_comes_out(simplebar, axes, tmp_path):
    out = tmp_path / "chart.svg"

    simplebar.run_all(dict(axes, out=str(out), format="svg"), bars(("alpha", 7)))
    svg = out.read_text()

    assert svg.startswith("<svg")
    assert "alpha" in svg
