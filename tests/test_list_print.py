import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def list_print():
    return load_module(next(discovery.bundled_scripts_dir().rglob("list_print.py")))


@pytest.fixture
def wide(list_print, monkeypatch):
    """A terminal wide enough that nothing is dropped for want of room."""
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 200)


@pytest.fixture
def shown(list_print, capsys):
    """Run the script and hand back the table it wrote, line by line."""

    def run(args, records):
        list_print.run_all(args, records)
        written = capsys.readouterr()
        assert written.out == ""  # A table is for looking at, not for piping.
        return written.err.splitlines()

    return run


ISSUES = [
    {"key": "ENG-1", "summary": "Ship it", "points": 8},
    {"key": "ENG-22", "summary": "Ship the other one", "points": 13},
]


# --- the table ------------------------------------------------------------


def test_the_headers_are_the_fields(shown, wide):
    assert shown({}, ISSUES)[0].split() == ["key", "summary", "points"]


def test_there_is_a_rule_under_the_headers(shown, wide):
    lines = shown({}, ISSUES)

    assert set(lines[1]) == {"-", " "}
    assert len(lines[1]) == len(lines[0])


def test_a_record_is_a_row(shown, wide):
    lines = shown({}, ISSUES)

    assert "ENG-1" in lines[2] and "Ship it" in lines[2]
    assert "ENG-22" in lines[3] and "Ship the other one" in lines[3]


def test_columns_line_up(shown, wide):
    lines = shown({}, ISSUES)
    starts = [line.index("Ship") for line in lines[2:4]]

    assert starts[0] == starts[1]


def test_a_column_is_as_wide_as_the_widest_thing_in_it(shown, wide):
    lines = shown({}, [{"key": "a"}, {"key": "much longer"}])

    assert lines[1] == "-" * len("much longer")


def test_nothing_trails_off_the_end_of_a_row(shown, wide):
    for line in shown({}, ISSUES):
        assert line == line.rstrip()


def test_the_table_goes_to_stderr_and_nothing_to_stdout(list_print, wide, capsys):
    assert list_print.run_all({}, ISSUES) == []
    written = capsys.readouterr()

    assert written.out == ""
    assert "ENG-1" in written.err


def test_tee_hands_the_records_on_unchanged(list_print, wide, capsys):
    assert list_print.run_all({"tee": True}, ISSUES) == ISSUES


def test_the_count_is_reported(shown, wide):
    assert shown({}, ISSUES)[-1] == "2 records"


def test_one_record_is_said_in_the_singular(shown, wide):
    assert shown({}, ISSUES[:1])[-1] == "1 record"


def test_no_records_is_said_rather_than_drawn(shown, wide):
    assert shown({}, []) == ["no records to show"]


def test_records_with_no_fields_are_counted_and_not_drawn(shown, wide):
    lines = shown({}, [{}, {}])

    assert lines == ["2 records, with no fields to show"]


# --- which columns, and in what order -------------------------------------


def test_columns_come_in_the_order_they_were_first_seen(list_print):
    records = [{"b": 1, "a": 2}, {"c": 3, "a": 4}]

    assert list_print._every_column(records) == ["b", "a", "c"]


def test_a_field_only_some_records_have_is_still_a_column(shown, wide):
    lines = shown({}, [{"a": 1}, {"a": 2, "b": 3}])

    assert lines[0].split() == ["a", "b"]


def test_a_record_missing_a_field_shows_it_as_missing(shown, wide):
    lines = shown({}, [{"a": 1, "b": "here"}, {"a": 2}])

    assert lines[3].split() == ["2", "-"]


def test_named_columns_are_the_ones_shown(shown, wide):
    lines = shown({"columns": "points,key"}, ISSUES)

    assert lines[0].split() == ["points", "key"]


def test_a_named_column_no_record_has_is_still_a_column(shown, wide):
    lines = shown({"columns": "key,nope"}, ISSUES)

    assert lines[0].split() == ["key", "nope"]
    assert lines[2].split() == ["ENG-1", "-"]


def test_columns_naming_nothing_is_refused(list_print):
    with pytest.raises(ValueError) as excinfo:
        list_print._named_columns({"columns": " , "})
    assert "names no columns" in str(excinfo.value)


def test_columns_has_to_be_named(list_print):
    with pytest.raises(ArgumentError) as excinfo:
        list_print._named_columns({"columns": True})
    assert "--columns must be text" in str(excinfo.value)


# --- fitting to the terminal ----------------------------------------------


def columns_of(*widths):
    return [{"width": width} for width in widths]


def test_columns_that_fit_are_all_kept(list_print, monkeypatch):
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 80)

    assert list_print._fitted(columns_of(10, 10, 10)) == [0, 1, 2]


def test_a_column_with_no_room_left_is_dropped(list_print, monkeypatch):
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 24)

    assert list_print._fitted(columns_of(10, 10, 10)) == [0, 1]


def test_a_column_too_wide_is_passed_over_rather_than_ending_the_table(
    list_print, monkeypatch
):
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 24)

    # The 40 does not fit; the narrow ones after it still do.
    assert list_print._fitted(columns_of(5, 40, 5, 5)) == [0, 2, 3]


def test_the_first_column_is_kept_however_wide_it_is(list_print, monkeypatch):
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 10)

    assert list_print._fitted(columns_of(80, 80)) == [0]


def test_what_was_dropped_is_named(shown, list_print, monkeypatch):
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 12)

    footer = shown({}, ISSUES)[-1]

    assert "2 more columns not shown (summary, points)" in footer
    assert "--columns" in footer


def test_one_dropped_column_is_said_in_the_singular(shown, list_print, monkeypatch):
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 26)

    assert "1 more column not shown (points)" in shown({}, ISSUES)[-1]


def test_named_columns_are_never_dropped_for_want_of_room(shown, list_print, monkeypatch):
    monkeypatch.setattr(list_print, "_terminal_width", lambda: 12)

    lines = shown({"columns": "key,summary,points"}, ISSUES)

    assert lines[0].split() == ["key", "summary", "points"]
    assert lines[-1] == "2 records"


# --- how a value reads ----------------------------------------------------


def test_text_is_itself(list_print):
    assert list_print._cell("Ship it", False) == "Ship it"


def test_a_null_and_a_missing_field_read_the_same(list_print):
    assert list_print._cell(None, False) == "-"


def test_an_empty_string_is_shown_as_missing(list_print):
    assert list_print._cell("   ", False) == "-"


def test_a_number_is_spelled_plainly(list_print):
    assert list_print._cell(8, False) == "8"
    assert list_print._cell(1.5, False) == "1.5"


def test_a_boolean_is_spelled_the_way_json_spells_it(list_print):
    assert list_print._cell(True, False) == "true"
    assert list_print._cell(False, False) == "false"


def test_a_nested_object_is_shown_by_its_name(list_print):
    assert list_print._cell({"name": "Done", "id": "3"}, False) == "Done"


def test_a_person_is_shown_by_the_name_they_display_under(list_print):
    who = {"displayName": "Ada Lovelace", "name": "ada", "id": "1"}

    assert list_print._cell(who, False) == "Ada Lovelace"


def test_an_object_with_no_name_is_shown_whole(list_print):
    assert list_print._cell({"b": 1, "a": 2}, False) == '{"a":2,"b":1}'


def test_an_object_named_by_another_object_is_shown_whole(list_print):
    got = list_print._cell({"name": {"first": "Ada"}}, False)

    assert got == '{"name":{"first":"Ada"}}'


def test_a_list_reads_as_its_elements(list_print):
    assert list_print._cell(["backend", "urgent"], False) == "backend, urgent"


def test_a_list_of_objects_reads_as_their_names(list_print):
    components = [{"name": "api"}, {"name": "web"}]

    assert list_print._cell(components, False) == "api, web"


def test_an_empty_list_is_shown_as_missing(list_print):
    assert list_print._cell([], False) == "-"


def test_line_breaks_are_taken_out(list_print):
    assert list_print._cell("two\nlines\there", False) == "two lines here"


def test_raw_shows_a_value_as_the_json_it_is(list_print):
    assert list_print._cell({"name": "Done"}, True) == '{"name":"Done"}'
    assert list_print._cell("Ship it", True) == '"Ship it"'
    assert list_print._cell(None, True) == "null"


# --- width ----------------------------------------------------------------


def test_a_long_value_is_cut_short(shown, wide):
    lines = shown({"width": 10}, [{"a": "far longer than ten"}])

    assert lines[2] == "far lon..."


def test_what_fits_is_left_alone(list_print):
    assert list_print._short("short", 10) == "short"


def test_a_value_exactly_as_wide_as_its_column_is_left_alone(list_print):
    assert list_print._short("exactly10!", 10) == "exactly10!"


def test_a_header_is_cut_short_the_same_way(shown, wide):
    lines = shown({"width": 6}, [{"a_very_long_field": 1}])

    assert lines[0] == "a_v..."


def test_the_width_has_to_be_a_number(list_print):
    with pytest.raises(ArgumentError) as excinfo:
        list_print._width({"width": "wide"})
    assert "--width must be a whole number" in str(excinfo.value)


def test_a_width_too_narrow_to_say_anything_is_refused(list_print):
    with pytest.raises(ValueError) as excinfo:
        list_print._width({"width": 2})
    assert "--width must be at least 4" in str(excinfo.value)


# --- lining up ------------------------------------------------------------


def test_numbers_line_up_on_the_right(shown, wide):
    lines = shown({}, [{"n": 1}, {"n": 1000}])

    assert lines[2].endswith("   1")
    assert lines[3].endswith("1000")


def test_a_column_of_numbers_with_a_gap_in_it_still_lines_up_right(list_print):
    assert list_print._is_number_column(["1", "-", "1000"]) is True


def test_words_line_up_on_the_left(list_print):
    assert list_print._is_number_column(["1", "one"]) is False


def test_a_column_of_nothing_but_gaps_is_not_a_column_of_numbers(list_print):
    assert list_print._is_number_column(["-", "-"]) is False
