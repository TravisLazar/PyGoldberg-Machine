"""Give each Jira issue a day-by-day changelog: what a field was, every day.

    $ pgm --jql='project = ENG' jira | pgm --fields=status jira_history
    jira_history: fetched the history of 12 issues
    {"key": "ENG-7", "status": {...}, "changelog": {"2026-02-03": {"status": "To Do"}, ...}}

Jira remembers changes, not days. Its history says a status went from To Do to
In Progress at 10:22 on a Tuesday and says nothing whatever about the Wednesday
after, which is the wrong shape for almost every report anybody wants: how many
issues were In Progress each day, how long one sat in review, what the board
looked like a month ago. So this walks each issue's history and writes down what
the field was at the end of every day in the window, whether anything happened
that day or not. Every record comes back with a `changelog`, keyed by date:

    "changelog": {
      "2026-02-03": {"status": "To Do"},
      "2026-02-04": {"status": "In Progress"},
      ...
    }

--fields says which fields to follow, as one comma-separated list; without it,
status. Each day holds one entry per field, so a day is a row and the fields are
its columns, and the shape does not change when a second field is asked for.

Values are text, the way Jira's own history writes them -- "In Progress" rather
than the object the issue carries -- because two days can then be compared,
counted and grouped. A change made during a day shows on that day: what is
written down is the state at the end of it, in UTC. Days before the issue
existed are null rather than the value it was first given, which is worth having
when a six-month window is asked of a two-week-old issue; that needs `created`
to have been fetched with the issue, and without it the earliest known value
simply runs back to the start of the window.

The window is the last six months, ending today. --months=N goes back further or
less far, and --since=YYYY-MM-DD and --until=YYYY-MM-DD say outright. --since
and --months both say where to start, so giving both is an error rather than a
guess about which was meant.

The history itself comes from Jira, one request per issue, from the same site
and the same account jira asks as -- JIRA_URL, JIRA_API_EMAIL and JIRA_API_TOKEN,
or --url, --email and --token. An issue that already carries Jira's own
changelog is read rather than asked about, so a pipeline that fetched with
expand=changelog costs nothing here.
"""

import base64
import calendar
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pgm import get_int, get_str, log

#: Where each setting comes from when it is not given on the line. The same
#: names jira uses, because it is the same site being asked.
URL_ENV = "JIRA_URL"
EMAIL_ENV = "JIRA_API_EMAIL"
TOKEN_ENV = "JIRA_API_TOKEN"

#: One issue's history, oldest first, paged with startAt.
CHANGELOG_PATH = "/rest/api/3/issue/%s/changelog"

#: How many history entries to ask for at once.
PAGE_SIZE = 100

#: How long one request may take. Long enough for a slow site to answer, short
#: enough that a pipeline waiting on it eventually stops waiting.
TIMEOUT = 60

#: How often to say how far along the fetching is. One request per issue is
#: slow enough on a big query to be worth reporting on.
PROGRESS_EVERY = 25

#: Which fields to follow when nobody says. Status is what a history is nearly
#: always asked about.
DEFAULT_FIELDS = "status"

#: How far back the window reaches when nobody says.
DEFAULT_MONTHS = 6

#: What the changelog is called on the record, and how its days are spelled.
CHANGELOG_KEY = "changelog"
DAY_FORMAT = "%Y-%m-%d"

#: What the issue is called, and when it began.
KEY_FIELD = "key"
CREATED_FIELD = "created"

#: Where an object keeps the name a person would read: a status and a priority
#: have `name`, a user has `displayName`, a select field has `value`.
DISPLAY_KEYS = ("name", "displayName", "value", "key")


def run_all(args: dict, records: list) -> List[dict]:
    """Give every issue a changelog: one entry per day, per field followed."""
    fields = _fields(args)
    since, until = _window(args)
    site = None  # type: Optional[Dict[str, str]]
    asked = 0
    written = []  # type: List[dict]
    for record in records:
        histories = _carried_history(record)
        if histories is None:
            # Asked for only when something actually has to be fetched, so a
            # pipeline that already carries its history needs no credentials.
            if site is None:
                site = _site(args)
            histories = fetch_changelog(site, _key_of(record))
            asked += 1
            if asked % PROGRESS_EVERY == 0:
                log("fetched the history of", asked, "issues so far")
        entry = dict(record)
        entry[CHANGELOG_KEY] = timeline(record, histories, fields, since, until)
        written.append(entry)
    if asked:
        log("fetched the history of", asked, "issues")
    if written:
        log(
            "wrote", len(_days(since, until)), "days of", ", ".join(fields),
            "for", len(written), "issues",
        )
    return written


def timeline(
    record: dict,
    histories: List[dict],
    fields: List[str],
    since: date,
    until: date,
) -> Dict[str, Dict[str, Optional[str]]]:
    """What every field was, on every day from `since` to `until`."""
    born = _created_on(record)
    tracks = {field: _track(record, field, histories) for field in fields}
    return {
        day.strftime(DAY_FORMAT): {
            field: None if born is not None and day < born else _value_on(track, day)
            for field, track in tracks.items()
        }
        for day in _days(since, until)
    }


def fetch_changelog(site: Dict[str, str], key: str) -> List[dict]:
    """Every change ever made to one issue, a page at a time.

    A page that brings nothing back ends it whatever it says about being the
    last one: the alternative is a script that asks the same question forever.
    """
    histories = []  # type: List[dict]
    while True:
        page = _get_page(site, key, len(histories))
        found = _histories_in(page, key)
        histories.extend(found)
        if not found or page.get("isLast", True):
            return histories


# --- the days -------------------------------------------------------------


def _track(
    record: dict, field: str, histories: List[dict]
) -> Tuple[Optional[str], List[Tuple[date, Optional[str]]]]:
    """What the field was to begin with, and what each change made of it.

    A field that was never changed has only what the issue says it is now,
    which it must therefore have been all along. A field that was changed does
    not need the issue at all: the first change says what it was before, and
    every change after that says what it became.
    """
    changes = _changes_to(field, histories)
    if changes:
        return changes[0][1], [(day, made) for day, _, made in changes]
    if field not in record:
        raise ValueError(
            "issue %s has no %r and its history never changed one, so there is "
            "nothing to follow; ask jira for the field, with --fields"
            % (record.get(KEY_FIELD, "?"), field)
        )
    return _display(record[field], record, field), []


def _value_on(
    track: Tuple[Optional[str], List[Tuple[date, Optional[str]]]], day: date
) -> Optional[str]:
    """What the field was at the end of one day: the last change up to it."""
    value, changes = track
    for when, made in changes:
        if when > day:
            break
        value = made
    return value


def _changes_to(
    field: str, histories: List[dict]
) -> List[Tuple[date, Optional[str], Optional[str]]]:
    """Every change to one field, oldest first, as (day, before, after).

    Sorted by the moment rather than the day, so two changes on one afternoon
    stay in the order they happened and the later one is what that day shows.
    """
    found = []  # type: List[Tuple[datetime, Optional[str], Optional[str]]]
    for history in _each_history(histories):
        when = _moment(history.get("created"))
        for item in _each_item(history):
            if _is_field(item, field):
                found.append((when, _text(item.get("fromString")), _text(item.get("toString"))))
    found.sort(key=lambda change: change[0])
    return [(when.date(), before, after) for when, before, after in found]


def _is_field(item: dict, field: str) -> bool:
    """Whether one change was to the field being followed.

    Jira names a change twice -- `fieldId` for what the issue calls it,
    `field` for what a person reading the history calls it -- and a custom
    field's two names are nothing alike, so either one counts.
    """
    names = (item.get("fieldId"), item.get("field"))
    wanted = field.strip().lower()
    return any(isinstance(name, str) and name.strip().lower() == wanted for name in names)


def _days(since: date, until: date) -> List[date]:
    """Every day in the window, first to last, including both ends."""
    return [since + timedelta(days=offset) for offset in range((until - since).days + 1)]


def _created_on(record: dict) -> Optional[date]:
    """The day the issue began, if the issue was fetched with it."""
    created = record.get(CREATED_FIELD)
    if created is None:
        return None
    return _moment(created, "issue %s's %s" % (record.get(KEY_FIELD, "?"), CREATED_FIELD)).date()


# --- what a value is ------------------------------------------------------


def _display(value: Any, record: dict, field: str) -> Optional[str]:
    """One field's value as text, the way the history writes the same field."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(_display(each, record, field) or "" for each in value)
    if isinstance(value, dict):
        for name in DISPLAY_KEYS:
            if isinstance(value.get(name), str):
                return value[name]
    raise ValueError(
        "issue %s's %r is %s, and nothing in it says what to call it, so it "
        "cannot be compared with what the history says it used to be"
        % (record.get(KEY_FIELD, "?"), field, _shape(value))
    )


def _shape(value: Any) -> str:
    """A value described the way somebody would ask about it."""
    if isinstance(value, dict):
        return "an object with %s in it" % (", ".join(sorted(value)) or "nothing")
    return "a %s" % type(value).__name__


def _text(value: Any) -> Optional[str]:
    """What a change said the value was: text, or nothing at all."""
    return value if isinstance(value, str) else None


def _moment(created: Any, what: str = "a change") -> datetime:
    """When something happened, as an instant in UTC.

    Jira writes offsets without a colon -- 2026-02-03T10:22:33.123+0000 -- which
    is not what fromisoformat reads before Python 3.11, so the offset is put the
    way it is spelled everywhere else first.
    """
    if not isinstance(created, str):
        raise ValueError(
            "%s says it happened at %s, where a time was expected" % (what, _shape(created))
        )
    text = created.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    elif len(text) > 5 and text[-5] in "+-" and text[-3] != ":":
        text = text[:-2] + ":" + text[-2:]
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("%s happened at %r, which is not a time" % (what, created))
    if when.tzinfo is None:
        # Jira always says the offset; something that did not is taken at its
        # word rather than moved by a guess about where it was written.
        return when
    return when.astimezone(timezone.utc).replace(tzinfo=None)


# --- what to follow, and when -----------------------------------------------


def _fields(args: dict) -> List[str]:
    """Which fields to follow, in the order they were given."""
    named = [part.strip() for part in get_str(args, "fields", DEFAULT_FIELDS).split(",")]
    fields = [part for part in named if part]
    if not fields:
        raise ValueError("--fields names no fields; leave it out to follow status")
    return fields


def _window(args: dict) -> Tuple[date, date]:
    """The first and last day to write down."""
    if "since" in args and "months" in args:
        raise ValueError(
            "--since and --months both say where the window starts; give one or "
            "the other"
        )
    until = _date(args, "until", _today())
    since = _date(args, "since", _months_before(until, _months(args)))
    if since > until:
        raise ValueError(
            "the window starts on %s and ends on %s, which is before it began"
            % (since.strftime(DAY_FORMAT), until.strftime(DAY_FORMAT))
        )
    return since, until


def _date(args: dict, name: str, default: date) -> date:
    """One end of the window, if it was said outright."""
    if name not in args:
        return default
    given = get_str(args, name, cast_numbers=True).strip()
    try:
        return datetime.strptime(given, DAY_FORMAT).date()
    except ValueError:
        raise ValueError(
            "--%s must be a day written YYYY-MM-DD, got %r" % (name, given)
        )


def _months(args: dict) -> int:
    """How far back the window reaches."""
    months = get_int(args, "months", DEFAULT_MONTHS)
    if months < 1:
        raise ValueError("--months must be at least 1, got %d" % months)
    return months


def _months_before(day: date, months: int) -> date:
    """The same day of the month, that many months earlier.

    The last days of a long month have no answer in a short one, so they land
    on the last day of the month they reach: six months before the 31st of
    August is the 28th of February, not the 3rd of March.
    """
    reached = day.month - 1 - months
    year = day.year + reached // 12
    month = reached % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _today() -> date:
    """Today, in UTC, which is the clock the days are counted on."""
    return datetime.now(timezone.utc).date()


# --- the history itself -----------------------------------------------------


def _carried_history(record: dict) -> Optional[List[dict]]:
    """The history the issue already carries, or None if it carries none.

    Jira sends this when it is asked to expand the changelog, and reading it
    saves a request per issue. A record whose changelog is this script's own is
    refused rather than read: running twice over the same records is a mistake
    worth hearing about, not a history to try to make sense of.
    """
    carried = record.get(CHANGELOG_KEY)
    if carried is None:
        return None
    if isinstance(carried, dict) and isinstance(carried.get("histories"), list):
        return carried["histories"]
    if isinstance(carried, list):
        return carried
    raise ValueError(
        "issue %s already has a %r, and it is not one of Jira's; it was written "
        "over rather than read" % (record.get(KEY_FIELD, "?"), CHANGELOG_KEY)
    )


def _key_of(record: dict) -> str:
    """Which issue to ask about, which nothing else can stand in for."""
    key = record.get(KEY_FIELD)
    if not isinstance(key, str) or not key.strip():
        raise ValueError(
            "a record has no %r to ask Jira about; jira_history follows issues "
            "that jira fetched" % KEY_FIELD
        )
    return key.strip()


def _each_history(histories: Any) -> List[dict]:
    """The entries of one issue's history, or a complaint about their shape."""
    if not isinstance(histories, list):
        raise ValueError(
            "an issue's history is %s where a list of changes was expected"
            % type(histories).__name__
        )
    for history in histories:
        if not isinstance(history, dict):
            raise ValueError(
                "an issue's history has %s in it where a change was expected"
                % type(history).__name__
            )
    return histories


def _each_item(history: dict) -> List[dict]:
    """What one entry of the history actually changed."""
    items = history.get("items") or []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError("a change has %s where the fields it changed should be" % _shape(items))
    return items


def _histories_in(page: Any, key: str) -> List[dict]:
    """The changes in one answer, or a complaint about the shape of it."""
    if not isinstance(page, dict):
        raise ValueError(
            "Jira answered with %s where a page of %s's history was expected"
            % (type(page).__name__, key)
        )
    values = page.get("values", [])
    if not isinstance(values, list):
        raise ValueError(
            "Jira's page of %s's history has %s in it where the changes should be"
            % (key, type(values).__name__)
        )
    return values


# --- where to look, and who as ----------------------------------------------


def _site(args: dict) -> Dict[str, str]:
    """Which Jira to ask, and who to ask it as."""
    return {
        "url": _base_url(_setting(args, "url", URL_ENV)),
        "email": _setting(args, "email", EMAIL_ENV),
        "token": _setting(args, "token", TOKEN_ENV),
    }


def _setting(args: dict, name: str, env: str) -> str:
    """An option if there is one, the environment if not, an error if neither.

    Said outright wins, so a one-off run against another site is a longer
    command line rather than an edit to the environment it inherited. An option
    given with nothing in it is that mistake rather than the other.
    """
    if name in args:
        given = get_str(args, name).strip()
        if not given:
            raise ValueError("--%s was given with nothing in it" % name)
        return given
    value = os.environ.get(env, "").strip()
    if not value:
        raise ValueError(
            "--%s was not given and %s is not set; jira_history needs both the "
            "site and the account to ask it as" % (name, env)
        )
    return value


def _base_url(url: str) -> str:
    """The site, without the trailing slash that would double up in the path."""
    trimmed = url.rstrip("/")
    if not trimmed.startswith(("http://", "https://")):
        raise ValueError(
            "%r is not a site to ask; write the whole URL, like "
            "https://your-team.atlassian.net" % url
        )
    return trimmed


def _get_page(site: Dict[str, str], key: str, start: int) -> dict:
    """Ask for one page of one issue's history and decode what comes back."""
    path = CHANGELOG_PATH % urllib.parse.quote(key)
    query = urllib.parse.urlencode({"startAt": start, "maxResults": PAGE_SIZE})
    request = urllib.request.Request(
        "%s%s?%s" % (site["url"], path, query),
        headers={
            "Authorization": "Basic %s" % _credentials(site),
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # Before URLError, which it inherits from: a refusal Jira explained is
        # worth reading, and an issue that is gone is only explained this way.
        raise ValueError("Jira refused to give %s's history: %s" % (key, _refusal(exc)))
    except urllib.error.URLError as exc:
        raise ValueError("could not reach %s: %s" % (site["url"], exc.reason))
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("%s answered with something that is not JSON" % site["url"])


def _credentials(site: Dict[str, str]) -> str:
    """The email and token, as basic auth spells them."""
    pair = "%s:%s" % (site["email"], site["token"])
    return base64.b64encode(pair.encode("utf-8")).decode("ascii")


def _refusal(exc: urllib.error.HTTPError) -> str:
    """The status, and whatever Jira said about it."""
    detail = _problem(exc)
    if not detail and exc.code in (401, 403):
        detail = "check the email and API token (%s and %s)" % (EMAIL_ENV, TOKEN_ENV)
    return "%s %s%s" % (exc.code, exc.reason, ": %s" % detail if detail else "")


def _problem(exc: urllib.error.HTTPError) -> str:
    """What Jira wrote in the body of a refusal, if it wrote anything usable."""
    try:
        reported = json.loads(exc.read().decode("utf-8"))
    except Exception:
        # A refusal is already being reported; how badly the body was formed is
        # not the thing to report instead of it.
        return ""
    if not isinstance(reported, dict):
        return ""
    messages = [str(text) for text in reported.get("errorMessages") or []]
    errors = reported.get("errors")
    if isinstance(errors, dict):
        messages.extend("%s: %s" % (name, errors[name]) for name in sorted(errors))
    return "; ".join(messages)
