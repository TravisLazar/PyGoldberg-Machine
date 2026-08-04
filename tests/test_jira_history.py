import json
import urllib.error
from datetime import date

import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def history():
    return load_module(next(discovery.bundled_scripts_dir().rglob("jira_history.py")))


@pytest.fixture
def site(history, monkeypatch):
    """A site to ask, set the way most runs set it: in the environment."""
    monkeypatch.setenv(history.URL_ENV, "https://team.atlassian.net")
    monkeypatch.setenv(history.EMAIL_ENV, "someone@team.example")
    monkeypatch.setenv(history.TOKEN_ENV, "s3cret")
    return {
        "url": "https://team.atlassian.net",
        "email": "someone@team.example",
        "token": "s3cret",
    }


def changed(when, field, before, after, field_id=None):
    """One entry of Jira's history: one field, changed once."""
    item = {"field": field, "fromString": before, "toString": after}
    if field_id is not None:
        item["fieldId"] = field_id
    return {"created": when, "items": [item]}


def issue(key="ENG-1", **fields):
    return dict({"key": key}, **fields)


WINDOW = {"since": "2026-02-01", "until": "2026-02-05"}


def days(record):
    """The changelog of one record, as (day, values) pairs in order."""
    return sorted(record["changelog"].items())


class FakeJira:
    """Stands in for the site: hands out prepared pages, remembers the asking."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.asked = []

    def __call__(self, site, key, start):
        self.asked.append((key, start))
        return self.pages[len(self.asked) - 1]


# --- one entry per day ------------------------------------------------------


def test_every_day_in_the_window_gets_an_entry(history):
    got = history.timeline(
        issue(status={"name": "Done"}), [], ["status"], date(2026, 2, 1), date(2026, 2, 5)
    )

    assert list(sorted(got)) == [
        "2026-02-01",
        "2026-02-02",
        "2026-02-03",
        "2026-02-04",
        "2026-02-05",
    ]


def test_a_field_that_never_changed_is_what_it_is_now_all_along(history):
    got = history.timeline(
        issue(status={"name": "To Do"}), [], ["status"], date(2026, 2, 1), date(2026, 2, 3)
    )

    assert list(got.values()) == [{"status": "To Do"}] * 3


def test_a_change_shows_on_the_day_it_was_made_and_after(history):
    histories = [changed("2026-02-03T10:22:33.000+0000", "status", "To Do", "In Progress")]

    got = history.timeline(
        issue(status={"name": "In Progress"}),
        histories,
        ["status"],
        date(2026, 2, 1),
        date(2026, 2, 5),
    )

    assert [values["status"] for _, values in days({"changelog": got})] == [
        "To Do",
        "To Do",
        "In Progress",
        "In Progress",
        "In Progress",
    ]


def test_the_last_change_of_a_day_is_what_that_day_shows(history):
    histories = [
        changed("2026-02-03T16:00:00.000+0000", "status", "In Progress", "Done"),
        changed("2026-02-03T09:00:00.000+0000", "status", "To Do", "In Progress"),
    ]

    got = history.timeline(
        issue(status={"name": "Done"}), histories, ["status"], date(2026, 2, 2), date(2026, 2, 3)
    )

    assert got["2026-02-02"] == {"status": "To Do"}
    assert got["2026-02-03"] == {"status": "Done"}


def test_a_change_after_the_window_does_not_reach_back_into_it(history):
    histories = [changed("2026-03-09T09:00:00.000+0000", "status", "To Do", "Done")]

    got = history.timeline(
        issue(status={"name": "Done"}), histories, ["status"], date(2026, 2, 1), date(2026, 2, 2)
    )

    assert set(values["status"] for values in got.values()) == {"To Do"}


def test_a_day_holds_every_field_that_was_asked_for(history):
    histories = [
        changed("2026-02-02T09:00:00.000+0000", "status", "To Do", "Done"),
        changed("2026-02-03T09:00:00.000+0000", "assignee", None, "Ada"),
    ]

    got = history.timeline(
        issue(status={"name": "Done"}, assignee={"displayName": "Ada"}),
        histories,
        ["status", "assignee"],
        date(2026, 2, 1),
        date(2026, 2, 3),
    )

    assert got["2026-02-01"] == {"status": "To Do", "assignee": None}
    assert got["2026-02-02"] == {"status": "Done", "assignee": None}
    assert got["2026-02-03"] == {"status": "Done", "assignee": "Ada"}


def test_days_before_the_issue_existed_are_null(history):
    record = issue(status={"name": "To Do"}, created="2026-02-03T08:00:00.000+0000")

    got = history.timeline(record, [], ["status"], date(2026, 2, 1), date(2026, 2, 4))

    assert got["2026-02-02"] == {"status": None}
    assert got["2026-02-03"] == {"status": "To Do"}
    assert got["2026-02-04"] == {"status": "To Do"}


def test_without_created_the_earliest_value_runs_back_to_the_start(history):
    got = history.timeline(
        issue(status={"name": "To Do"}), [], ["status"], date(2026, 2, 1), date(2026, 2, 2)
    )

    assert got["2026-02-01"] == {"status": "To Do"}


def test_one_day_is_a_window_too(history):
    got = history.timeline(
        issue(status={"name": "Done"}), [], ["status"], date(2026, 2, 1), date(2026, 2, 1)
    )

    assert got == {"2026-02-01": {"status": "Done"}}


# --- what a value is --------------------------------------------------------


def test_an_object_becomes_the_name_a_person_reads(history):
    record = issue(status={"name": "In Review", "id": "10001"})

    got = history.timeline(record, [], ["status"], date(2026, 2, 1), date(2026, 2, 1))

    assert got["2026-02-01"] == {"status": "In Review"}


def test_a_user_becomes_their_display_name(history):
    record = issue(assignee={"accountId": "abc", "displayName": "Ada Lovelace"})

    got = history.timeline(record, [], ["assignee"], date(2026, 2, 1), date(2026, 2, 1))

    assert got["2026-02-01"] == {"assignee": "Ada Lovelace"}


def test_a_number_is_written_down_as_text(history):
    record = issue(customfield_10016=5)

    got = history.timeline(record, [], ["customfield_10016"], date(2026, 2, 1), date(2026, 2, 1))

    assert got["2026-02-01"] == {"customfield_10016": "5"}


def test_a_field_with_nothing_in_it_is_null(history):
    record = issue(resolution=None)

    got = history.timeline(record, [], ["resolution"], date(2026, 2, 1), date(2026, 2, 1))

    assert got["2026-02-01"] == {"resolution": None}


def test_several_values_are_written_the_way_the_history_writes_them(history):
    record = issue(labels=["backend", "urgent"])

    got = history.timeline(record, [], ["labels"], date(2026, 2, 1), date(2026, 2, 1))

    assert got["2026-02-01"] == {"labels": "backend, urgent"}


def test_an_object_with_no_name_in_it_is_reported(history):
    record = issue(votes={"votes": 3, "hasVoted": False})

    with pytest.raises(ValueError) as excinfo:
        history.timeline(record, [], ["votes"], date(2026, 2, 1), date(2026, 2, 1))
    assert "nothing in it says what to call it" in str(excinfo.value)


def test_a_field_that_was_never_fetched_or_changed_is_reported(history):
    with pytest.raises(ValueError) as excinfo:
        history.timeline(issue(), [], ["status"], date(2026, 2, 1), date(2026, 2, 1))
    message = str(excinfo.value)
    assert "ENG-1" in message and "--fields" in message


# --- which change is which --------------------------------------------------


def test_a_change_to_another_field_is_left_alone(history):
    histories = [changed("2026-02-02T09:00:00.000+0000", "summary", "old", "new")]

    got = history.timeline(
        issue(status={"name": "To Do"}), histories, ["status"], date(2026, 2, 1), date(2026, 2, 3)
    )

    assert set(values["status"] for values in got.values()) == {"To Do"}


def test_a_custom_field_is_found_by_its_id(history):
    histories = [
        changed("2026-02-02T09:00:00.000+0000", "Story Points", "3", "5", "customfield_10016")
    ]

    got = history.timeline(
        issue(), histories, ["customfield_10016"], date(2026, 2, 1), date(2026, 2, 2)
    )

    assert [got["2026-02-01"], got["2026-02-02"]] == [
        {"customfield_10016": "3"},
        {"customfield_10016": "5"},
    ]


def test_a_custom_field_is_found_by_the_name_it_is_shown_under(history):
    histories = [
        changed("2026-02-02T09:00:00.000+0000", "Story Points", "3", "5", "customfield_10016")
    ]

    got = history.timeline(issue(), histories, ["Story Points"], date(2026, 2, 1), date(2026, 2, 2))

    assert got["2026-02-02"] == {"Story Points": "5"}


def test_a_change_to_nothing_is_null_rather_than_text(history):
    histories = [changed("2026-02-02T09:00:00.000+0000", "assignee", "Ada", None)]

    got = history.timeline(
        issue(assignee=None), histories, ["assignee"], date(2026, 2, 1), date(2026, 2, 2)
    )

    assert [got["2026-02-01"], got["2026-02-02"]] == [{"assignee": "Ada"}, {"assignee": None}]


def test_a_change_says_what_the_field_was_before_the_issue_was_asked_about(history):
    # The issue itself was never asked for the field; the history alone has it.
    histories = [changed("2026-02-02T09:00:00.000+0000", "status", "To Do", "Done")]

    got = history.timeline(issue(), histories, ["status"], date(2026, 2, 1), date(2026, 2, 2))

    assert [got["2026-02-01"], got["2026-02-02"]] == [{"status": "To Do"}, {"status": "Done"}]


# --- times ------------------------------------------------------------------


def test_a_time_is_read_in_utc(history):
    # 23:30 in Sydney on the 4th is the 4th in UTC, not the 5th.
    when = history._moment("2026-02-04T23:30:00.000+1100")

    assert when.date() == date(2026, 2, 4)


def test_a_time_written_with_a_z_is_read_too(history):
    assert history._moment("2026-02-04T10:00:00Z").date() == date(2026, 2, 4)


def test_something_that_is_not_a_time_is_reported(history):
    with pytest.raises(ValueError) as excinfo:
        history._moment("last tuesday")
    assert "which is not a time" in str(excinfo.value)


def test_a_change_with_no_time_on_it_is_reported(history):
    with pytest.raises(ValueError) as excinfo:
        history.timeline(issue(), [{"items": []}], ["status"], date(2026, 2, 1), date(2026, 2, 1))
    assert "where a time was expected" in str(excinfo.value)


# --- the window -------------------------------------------------------------


def test_the_window_is_six_months_back_by_default(history, monkeypatch):
    monkeypatch.setattr(history, "_today", lambda: date(2026, 8, 3))

    assert history._window({}) == (date(2026, 2, 3), date(2026, 8, 3))


def test_the_months_can_be_said(history, monkeypatch):
    monkeypatch.setattr(history, "_today", lambda: date(2026, 8, 3))

    assert history._window({"months": 1}) == (date(2026, 7, 3), date(2026, 8, 3))


def test_both_ends_can_be_said_outright(history):
    assert history._window(WINDOW) == (date(2026, 2, 1), date(2026, 2, 5))


def test_the_months_are_counted_back_from_the_end_that_was_said(history):
    assert history._window({"until": "2026-08-03", "months": 6})[0] == date(2026, 2, 3)


def test_a_day_a_shorter_month_does_not_have_lands_on_its_last(history):
    assert history._months_before(date(2026, 8, 31), 6) == date(2026, 2, 28)


def test_saying_where_to_start_twice_is_refused(history):
    with pytest.raises(ValueError) as excinfo:
        history._window({"since": "2026-02-01", "months": 3})
    assert "give one or the other" in str(excinfo.value)


def test_a_window_that_ends_before_it_starts_is_refused(history):
    with pytest.raises(ValueError) as excinfo:
        history._window({"since": "2026-03-01", "until": "2026-02-01"})
    assert "before it began" in str(excinfo.value)


def test_a_day_written_some_other_way_is_refused(history):
    with pytest.raises(ValueError) as excinfo:
        history._window({"since": "01/02/2026"})
    assert "--since must be a day written YYYY-MM-DD" in str(excinfo.value)


def test_months_that_are_not_a_number_are_refused(history):
    with pytest.raises(ArgumentError) as excinfo:
        history._window({"months": "six"})
    assert "--months must be a whole number" in str(excinfo.value)


def test_a_window_of_no_months_is_refused(history):
    with pytest.raises(ValueError) as excinfo:
        history._window({"months": 0})
    assert "--months must be at least 1" in str(excinfo.value)


# --- which fields -----------------------------------------------------------


def test_status_is_followed_when_nobody_says(history):
    assert history._fields({}) == [history.DEFAULT_FIELDS] == ["status"]


def test_fields_are_one_comma_separated_list(history):
    assert history._fields({"fields": "status, assignee ,priority"}) == [
        "status",
        "assignee",
        "priority",
    ]


def test_fields_naming_nothing_is_refused(history):
    with pytest.raises(ValueError) as excinfo:
        history._fields({"fields": " , "})
    assert "names no fields" in str(excinfo.value)


# --- the history that arrives with the issue --------------------------------


def test_a_carried_changelog_is_read_rather_than_asked_about(history, monkeypatch):
    monkeypatch.setattr(history, "_get_page", _never_asked)
    record = issue(
        status={"name": "Done"},
        changelog={"histories": [changed("2026-02-03T09:00:00.000+0000", "status", "To Do", "Done")]},
    )

    got = history.run_all(dict(WINDOW), [record])

    assert got[0]["changelog"]["2026-02-02"] == {"status": "To Do"}
    assert got[0]["changelog"]["2026-02-03"] == {"status": "Done"}


def test_a_carried_changelog_needs_no_credentials(history, monkeypatch):
    for name in (history.URL_ENV, history.EMAIL_ENV, history.TOKEN_ENV):
        monkeypatch.delenv(name, raising=False)
    record = issue(status={"name": "Done"}, changelog={"histories": []})

    assert history.run_all(dict(WINDOW), [record])[0]["changelog"]


def test_a_changelog_this_script_wrote_is_refused(history, site):
    record = issue(status={"name": "Done"}, changelog={"2026-02-01": {"status": "Done"}})

    with pytest.raises(ValueError) as excinfo:
        history.run_all(dict(WINDOW), [record])
    assert "written over rather than read" in str(excinfo.value)


def test_an_issue_with_no_key_cannot_be_asked_about(history, site):
    with pytest.raises(ValueError) as excinfo:
        history.run_all(dict(WINDOW), [{"status": {"name": "Done"}}])
    assert "no 'key' to ask Jira about" in str(excinfo.value)


def test_a_history_that_is_not_a_list_is_reported(history):
    with pytest.raises(ValueError) as excinfo:
        history.timeline(issue(), {"items": []}, ["status"], date(2026, 2, 1), date(2026, 2, 1))
    assert "where a list of changes was expected" in str(excinfo.value)


def test_a_change_that_is_not_a_change_is_reported(history):
    with pytest.raises(ValueError) as excinfo:
        history.timeline(issue(), ["moved it"], ["status"], date(2026, 2, 1), date(2026, 2, 1))
    assert "where a change was expected" in str(excinfo.value)


def _never_asked(*args, **kwargs):
    raise AssertionError("Jira was asked about an issue that carried its history")


# --- fetching ---------------------------------------------------------------


def test_the_history_is_fetched_for_each_issue(history, site, monkeypatch):
    fake = FakeJira(
        {"values": [changed("2026-02-02T09:00:00.000+0000", "status", "To Do", "Done")], "isLast": True},
        {"values": [], "isLast": True},
    )
    monkeypatch.setattr(history, "_get_page", fake)

    got = history.run_all(dict(WINDOW), [issue("ENG-1", status={"name": "Done"}), issue("ENG-2", status={"name": "To Do"})])

    assert [key for key, _ in fake.asked] == ["ENG-1", "ENG-2"]
    assert got[0]["changelog"]["2026-02-01"] == {"status": "To Do"}
    assert got[1]["changelog"]["2026-02-05"] == {"status": "To Do"}


def test_pages_of_history_are_followed_to_the_end(history, site, monkeypatch):
    fake = FakeJira(
        {"values": [changed("2026-02-01T09:00:00.000+0000", "status", "To Do", "Doing")], "isLast": False},
        {"values": [changed("2026-02-03T09:00:00.000+0000", "status", "Doing", "Done")], "isLast": True},
    )
    monkeypatch.setattr(history, "_get_page", fake)

    got = history.fetch_changelog(site, "ENG-1")

    assert len(got) == 2
    assert [start for _, start in fake.asked] == [0, 1]


def test_a_page_with_nothing_on_it_ends_the_fetch(history, site, monkeypatch):
    fake = FakeJira({"values": [], "isLast": False})
    monkeypatch.setattr(history, "_get_page", fake)

    assert history.fetch_changelog(site, "ENG-1") == []
    assert len(fake.asked) == 1


def test_an_answer_that_is_not_a_page_is_reported(history, site, monkeypatch):
    monkeypatch.setattr(history, "_get_page", FakeJira(["not", "a", "page"]))

    with pytest.raises(ValueError) as excinfo:
        history.fetch_changelog(site, "ENG-1")
    assert "where a page of ENG-1's history was expected" in str(excinfo.value)


def test_a_page_whose_changes_are_not_a_list_is_reported(history, site, monkeypatch):
    monkeypatch.setattr(history, "_get_page", FakeJira({"values": "lots"}))

    with pytest.raises(ValueError) as excinfo:
        history.fetch_changelog(site, "ENG-1")
    assert "where the changes should be" in str(excinfo.value)


# --- the records that come out ----------------------------------------------


def test_the_issue_is_handed_on_with_its_changelog(history, site, monkeypatch):
    monkeypatch.setattr(history, "_get_page", FakeJira({"values": [], "isLast": True}))

    got = history.run_all(dict(WINDOW), [issue(status={"name": "Done"}, summary="Ship it")])

    assert got[0]["key"] == "ENG-1"
    assert got[0]["summary"] == "Ship it"
    assert len(got[0]["changelog"]) == 5


def test_the_records_that_arrived_are_left_as_they_were(history, site, monkeypatch):
    monkeypatch.setattr(history, "_get_page", FakeJira({"values": [], "isLast": True}))
    record = issue(status={"name": "Done"})

    history.run_all(dict(WINDOW), [record])

    assert "changelog" not in record


def test_no_issues_is_no_records(history, site):
    assert history.run_all(dict(WINDOW), []) == []


# --- where to look, and who as ----------------------------------------------


def test_the_environment_says_where_to_look(history, site):
    assert history._site({}) == site


def test_an_option_beats_the_environment(history, site):
    got = history._site({"url": "https://other.atlassian.net"})

    assert got["url"] == "https://other.atlassian.net"
    assert got["email"] == site["email"]


def test_a_setting_given_nowhere_is_reported(history, monkeypatch):
    monkeypatch.delenv(history.URL_ENV, raising=False)
    monkeypatch.setenv(history.EMAIL_ENV, "someone@team.example")
    monkeypatch.setenv(history.TOKEN_ENV, "s3cret")

    with pytest.raises(ValueError) as excinfo:
        history._site({})
    assert "--url was not given" in str(excinfo.value)


def test_something_that_is_not_a_url_is_refused(history):
    with pytest.raises(ValueError) as excinfo:
        history._base_url("team.atlassian.net")
    assert "write the whole URL" in str(excinfo.value)


# --- what Jira says when it says no -----------------------------------------


def test_what_jira_said_is_what_is_reported(history):
    said = urllib.error.HTTPError(
        "https://team.atlassian.net", 404, "Not Found", {}, _Body({"errorMessages": ["gone"]})
    )

    assert "gone" in history._refusal(said)


def test_being_turned_away_points_at_the_credentials(history):
    said = urllib.error.HTTPError(
        "https://team.atlassian.net", 401, "Unauthorized", {}, _Body({})
    )
    message = history._refusal(said)

    assert history.EMAIL_ENV in message and history.TOKEN_ENV in message


class _Body:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        pass
