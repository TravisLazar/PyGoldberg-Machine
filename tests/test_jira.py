import json
import urllib.error

import pytest

from pgm import discovery
from pgm.errors import ArgumentError
from pgm.runner import load_module


@pytest.fixture(scope="module")
def jira():
    return load_module(next(discovery.bundled_scripts_dir().rglob("jira.py")))


@pytest.fixture
def site(jira, monkeypatch):
    """A site to ask, set the way most runs set it: in the environment."""
    monkeypatch.setenv(jira.URL_ENV, "https://team.atlassian.net")
    monkeypatch.setenv(jira.EMAIL_ENV, "someone@team.example")
    monkeypatch.setenv(jira.TOKEN_ENV, "s3cret")
    return {
        "url": "https://team.atlassian.net",
        "email": "someone@team.example",
        "token": "s3cret",
    }


def issues(*keys):
    return [{"id": str(index), "key": key} for index, key in enumerate(keys)]


class FakeJira:
    """Stands in for the site: hands out prepared pages, remembers the asking."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.bodies = []

    def __call__(self, site, body):
        self.bodies.append(body)
        return self.pages[len(self.bodies) - 1]


def paged(*keys, **extra):
    """One page of results, with whatever else the answer carried."""
    return dict({"issues": list(issues(*keys))}, **extra)


# --- paging ---------------------------------------------------------------


def test_one_page_is_one_request(jira, site, monkeypatch):
    fake = FakeJira(paged("ENG-1", "ENG-2"))
    monkeypatch.setattr(jira, "_post_page", fake)

    got = jira.fetch(site, "project = ENG", ["summary"])

    assert [issue["key"] for issue in got] == ["ENG-1", "ENG-2"]
    assert len(fake.bodies) == 1


def test_pages_are_followed_to_the_end(jira, site, monkeypatch):
    fake = FakeJira(
        paged("ENG-1", nextPageToken="two"),
        paged("ENG-2", nextPageToken="three"),
        paged("ENG-3"),
    )
    monkeypatch.setattr(jira, "_post_page", fake)

    got = jira.fetch(site, "project = ENG", ["summary"])

    assert [issue["key"] for issue in got] == ["ENG-1", "ENG-2", "ENG-3"]
    assert [body.get("nextPageToken") for body in fake.bodies] == [None, "two", "three"]


def test_an_empty_page_ends_it_whatever_it_says(jira, site, monkeypatch):
    # A next-page token on a page with nothing on it would otherwise be a loop.
    fake = FakeJira(paged("ENG-1", nextPageToken="two"), paged(nextPageToken="three"))
    monkeypatch.setattr(jira, "_post_page", fake)

    got = jira.fetch(site, "project = ENG", ["summary"])

    assert [issue["key"] for issue in got] == ["ENG-1"]
    assert len(fake.bodies) == 2


def test_nothing_matching_is_no_records(jira, site, monkeypatch):
    monkeypatch.setattr(jira, "_post_page", FakeJira(paged()))

    assert jira.fetch(site, "project = NONE", ["summary"]) == []


def test_a_full_page_is_asked_for_when_there_is_no_limit(jira, site, monkeypatch):
    fake = FakeJira(paged("ENG-1"))
    monkeypatch.setattr(jira, "_post_page", fake)

    jira.fetch(site, "project = ENG", ["summary"])

    assert fake.bodies[0]["maxResults"] == jira.PAGE_SIZE


def test_the_request_carries_the_query_and_the_fields(jira, site, monkeypatch):
    fake = FakeJira(paged("ENG-1"))
    monkeypatch.setattr(jira, "_post_page", fake)

    jira.fetch(site, "project = ENG", ["summary", "status"])

    assert fake.bodies[0]["jql"] == "project = ENG"
    assert fake.bodies[0]["fields"] == ["summary", "status"]


# --- the limit ------------------------------------------------------------


def test_the_limit_stops_the_fetch(jira, site, monkeypatch):
    fake = FakeJira(paged("ENG-1", "ENG-2", nextPageToken="two"))
    monkeypatch.setattr(jira, "_post_page", fake)

    got = jira.fetch(site, "project = ENG", ["summary"], limit=2)

    assert [issue["key"] for issue in got] == ["ENG-1", "ENG-2"]
    assert len(fake.bodies) == 1


def test_only_what_is_left_of_the_limit_is_asked_for(jira, site, monkeypatch):
    fake = FakeJira(paged("ENG-1", nextPageToken="two"), paged("ENG-2", "ENG-3"))
    monkeypatch.setattr(jira, "_post_page", fake)

    jira.fetch(site, "project = ENG", ["summary"], limit=3)

    assert [body["maxResults"] for body in fake.bodies] == [3, 2]


def test_a_page_longer_than_the_limit_is_trimmed(jira, site, monkeypatch):
    monkeypatch.setattr(jira, "_post_page", FakeJira(paged("ENG-1", "ENG-2", "ENG-3")))

    got = jira.fetch(site, "project = ENG", ["summary"], limit=2)

    assert [issue["key"] for issue in got] == ["ENG-1", "ENG-2"]


def test_a_limit_beyond_what_matched_is_just_what_matched(jira, site, monkeypatch):
    monkeypatch.setattr(jira, "_post_page", FakeJira(paged("ENG-1")))

    got = jira.fetch(site, "project = ENG", ["summary"], limit=50)

    assert [issue["key"] for issue in got] == ["ENG-1"]


def test_the_limit_has_to_be_a_number(jira):
    with pytest.raises(ArgumentError) as excinfo:
        jira._limit({"max_records": "lots"})
    assert "--max-records must be a whole number" in str(excinfo.value)


def test_a_limit_of_nothing_is_refused(jira):
    with pytest.raises(ValueError) as excinfo:
        jira._limit({"max_records": 0})
    assert "--max-records must be at least 1" in str(excinfo.value)


def test_no_limit_means_no_limit(jira):
    assert jira._limit({}) is None


# --- the records that come out --------------------------------------------


def test_fields_are_lifted_up_beside_the_key(jira):
    issue = {"id": "1", "key": "ENG-1", "self": "https://...", "fields": {"summary": "x"}}

    assert jira._record(issue) == {"id": "1", "key": "ENG-1", "summary": "x"}


def test_an_issue_with_no_fields_is_still_a_record(jira):
    assert jira._record({"id": "1", "key": "ENG-1"}) == {"id": "1", "key": "ENG-1"}


def test_a_field_that_collides_with_the_key_is_refused(jira):
    issue = {"id": "1", "key": "ENG-1", "fields": {"key": "something else"}}

    with pytest.raises(ValueError) as excinfo:
        jira._record(issue)
    assert "written over" in str(excinfo.value)


def test_a_nested_field_keeps_its_shape(jira):
    issue = {"key": "ENG-1", "fields": {"status": {"name": "Done"}}}

    assert jira._record(issue)["status"] == {"name": "Done"}


def test_run_all_returns_a_record_per_issue(jira, site, monkeypatch):
    monkeypatch.setattr(
        jira,
        "_post_page",
        FakeJira({"issues": [{"key": "ENG-1", "fields": {"summary": "x"}}]}),
    )

    got = jira.run_all({"jql": "project = ENG"}, [])

    assert got == [{"key": "ENG-1", "summary": "x"}]


def test_records_arriving_is_refused(jira, site, monkeypatch):
    monkeypatch.setattr(jira, "_post_page", FakeJira(paged("ENG-1")))

    with pytest.raises(ValueError) as excinfo:
        jira.run_all({"jql": "project = ENG"}, [{"key": "ENG-9"}])
    assert "starts a pipeline" in str(excinfo.value)


# --- what to fetch --------------------------------------------------------


def test_the_query_is_required(jira, site):
    with pytest.raises(ArgumentError) as excinfo:
        jira.run_all({}, [])
    assert "--jql is required" in str(excinfo.value)


def test_an_empty_query_is_refused(jira, site):
    with pytest.raises(ValueError) as excinfo:
        jira.run_all({"jql": "   "}, [])
    assert "--jql is empty" in str(excinfo.value)


def test_the_usual_fields_are_asked_for_when_nobody_says(jira):
    assert jira._fields({}) == [jira.DEFAULT_FIELDS]


def test_fields_are_one_comma_separated_list(jira):
    assert jira._fields({"fields": "summary, status ,assignee"}) == [
        "summary",
        "status",
        "assignee",
    ]


def test_fields_naming_nothing_is_refused(jira):
    with pytest.raises(ValueError) as excinfo:
        jira._fields({"fields": " , "})
    assert "names no fields" in str(excinfo.value)


# --- where to look, and who as --------------------------------------------


def test_the_environment_says_where_to_look(jira, site):
    assert jira._site({}) == site


def test_an_option_beats_the_environment(jira, site):
    got = jira._site({"url": "https://other.atlassian.net", "token": "other"})

    assert got["url"] == "https://other.atlassian.net"
    assert got["token"] == "other"
    assert got["email"] == site["email"]


def test_a_setting_given_nowhere_is_reported(jira, monkeypatch):
    monkeypatch.delenv(jira.URL_ENV, raising=False)
    monkeypatch.setenv(jira.EMAIL_ENV, "someone@team.example")
    monkeypatch.setenv(jira.TOKEN_ENV, "s3cret")

    with pytest.raises(ValueError) as excinfo:
        jira._site({})
    message = str(excinfo.value)
    assert "--url was not given" in message
    assert jira.URL_ENV in message


def test_an_option_with_nothing_in_it_does_not_fall_back(jira, site):
    # The environment has a token; --token= said to use another one, and did
    # not say which, so the answer is the mistake rather than the inherited one.
    with pytest.raises(ValueError) as excinfo:
        jira._site({"token": "   "})
    assert "--token was given with nothing in it" in str(excinfo.value)


def test_a_setting_that_needs_a_value_will_not_take_a_bare_flag(jira, site):
    with pytest.raises(ArgumentError) as excinfo:
        jira._site({"email": True})
    assert "--email must be text" in str(excinfo.value)


def test_a_trailing_slash_does_not_double_up(jira):
    assert jira._base_url("https://team.atlassian.net/") == "https://team.atlassian.net"


def test_something_that_is_not_a_url_is_refused(jira):
    with pytest.raises(ValueError) as excinfo:
        jira._base_url("team.atlassian.net")
    assert "write the whole URL" in str(excinfo.value)


def test_the_credentials_are_the_email_and_the_token(jira, site):
    import base64

    decoded = base64.b64decode(jira._credentials(site)).decode()

    assert decoded == "someone@team.example:s3cret"


# --- what Jira says when it says no ---------------------------------------


def refusal(code, reason, body):
    return urllib.error.HTTPError(
        "https://team.atlassian.net", code, reason, {}, _Body(body)
    )


class _Body:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def close(self):
        pass


def test_what_jira_said_is_what_is_reported(jira):
    said = refusal(400, "Bad Request", {"errorMessages": ["Field 'nope' does not exist"]})

    assert "Field 'nope' does not exist" in jira._refusal(said)


def test_field_errors_are_reported_too(jira):
    said = refusal(400, "Bad Request", {"errors": {"jql": "unable to parse"}})

    assert "jql: unable to parse" in jira._refusal(said)


def test_a_refusal_with_nothing_in_it_still_says_the_status(jira):
    said = refusal(500, "Server Error", {})

    assert "500 Server Error" in jira._refusal(said)


def test_being_turned_away_points_at_the_credentials(jira):
    said = refusal(401, "Unauthorized", {})
    message = jira._refusal(said)

    assert jira.EMAIL_ENV in message and jira.TOKEN_ENV in message


# --- answers that are not answers -----------------------------------------


def test_an_answer_that_is_not_a_page_is_reported(jira, site, monkeypatch):
    monkeypatch.setattr(jira, "_post_page", FakeJira(["not", "a", "page"]))

    with pytest.raises(ValueError) as excinfo:
        jira.fetch(site, "project = ENG", ["summary"])
    assert "where a page of issues was expected" in str(excinfo.value)


def test_a_page_whose_issues_are_not_a_list_is_reported(jira, site, monkeypatch):
    monkeypatch.setattr(jira, "_post_page", FakeJira({"issues": "ENG-1"}))

    with pytest.raises(ValueError) as excinfo:
        jira.fetch(site, "project = ENG", ["summary"])
    assert "where the issues should be" in str(excinfo.value)


def test_an_issue_that_is_not_an_issue_is_reported(jira):
    with pytest.raises(ValueError) as excinfo:
        jira._record("ENG-1")
    assert "where an issue was expected" in str(excinfo.value)
