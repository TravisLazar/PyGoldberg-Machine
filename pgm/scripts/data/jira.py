"""Fetch Jira issues by JQL, one record per issue.

    $ pgm --jql='project = ENG AND status = Done' --max-records=2 jira
    jira: fetched 2 issues from https://your-team.atlassian.net
    {"id": "10231", "key": "ENG-7", "summary": "Ship the thing", ...}
    {"id": "10232", "key": "ENG-9", "summary": "Ship the other thing", ...}

Which is where a report starts, because what comes back is records like any
other and the rest of pgm already knows what to do with those:

    $ pgm --jql='project = ENG' --fields=status jira |
      pgm --groupname=status groupcount |
      pgm --x=status --y=count --title=Backlog simplebar

Where to look and who is looking come from the environment -- JIRA_URL,
JIRA_API_EMAIL and JIRA_API_TOKEN -- so the usual run says only what to fetch,
and a token stays out of the shell history. Each can be said outright with
--url, --email or --token, for a second site or somebody else's account; what is
said outright wins over what was inherited.

Jira answers a page at a time, and this asks for the next page until there are
no more: --jql is answered in full, however long the answer is. --max-records
stops it early, which is the thing to reach for while a query is still being
written. It is a limit on records rather than on pages -- the last page asked
for is only as big as what is left of it -- so `--max-records=5` is five issues
and one request, not five issues and a hundred fetched to find them.

Each issue arrives flat: its `fields` are lifted up beside `key` and `id`,
because a record with everything nested a level down is not something the rest
of pgm can group, sort or plot. --fields says which fields to ask for, as one
comma-separated list; without it Jira sends the ones it navigates by.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from pgm import get_int, get_str, log

#: Where each setting comes from when it is not given on the line. Names Jira's
#: own tooling already uses, so a machine set up for Jira is set up for this.
URL_ENV = "JIRA_URL"
EMAIL_ENV = "JIRA_API_EMAIL"
TOKEN_ENV = "JIRA_API_TOKEN"

#: Jira Cloud's enhanced search: a page of issues, plus a token for the next
#: one. There is no total and no start offset -- paging is the token or nothing.
SEARCH_PATH = "/rest/api/3/search/jql"

#: How many issues to ask for at once, which is as many as this endpoint gives.
PAGE_SIZE = 100

#: Which fields to ask for when nobody says. Jira sends `id` and `key` alone
#: otherwise, and two identifiers are not a record worth piping anywhere.
DEFAULT_FIELDS = "*navigable"

#: How long one request may take. Long enough for a slow site to answer, short
#: enough that a pipeline waiting on it eventually stops waiting.
TIMEOUT = 60

#: What an issue carries beside its fields, and what a field therefore cannot
#: be called without one of the two being lost.
ISSUE_KEYS = ("id", "key")


def run_all(args: dict, records: list) -> List[dict]:
    """Fetch every issue the JQL matches, or as many as was asked for."""
    if records:
        raise ValueError(
            "%d records arrived, and jira fetches rather than reads: it starts "
            "a pipeline rather than standing in one" % len(records)
        )
    site = _site(args)
    issues = fetch(site, _jql(args), _fields(args), _limit(args))
    log("fetched", len(issues), "issues from", site["url"])
    return [_record(issue) for issue in issues]


def fetch(
    site: Dict[str, str],
    jql: str,
    fields: List[str],
    limit: Optional[int] = None,
) -> List[dict]:
    """Every issue matching the JQL, a page at a time, up to `limit`.

    A page that brings nothing back ends it whatever it says about a next one:
    Jira does not do that, and if it ever did, the alternative is a script that
    asks the same question forever.
    """
    issues = []  # type: List[dict]
    token = None  # type: Optional[str]
    while True:
        wanted = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(issues))
        page = _post_page(site, _body(jql, fields, wanted, token))
        found = _issues_in(page)
        issues.extend(found)
        token = page.get("nextPageToken")
        if limit is not None and len(issues) >= limit:
            return issues[:limit]
        if not found or not token:
            return issues
        log("fetched", len(issues), "so far")


def _body(jql: str, fields: List[str], wanted: int, token: Optional[str]) -> dict:
    """One request: what to match, what to send back, and where to carry on."""
    body = {"jql": jql, "fields": fields, "maxResults": wanted}
    if token is not None:
        body["nextPageToken"] = token
    return body


def _issues_in(page: Any) -> List[dict]:
    """The issues in one answer, or a complaint about the shape of it."""
    if not isinstance(page, dict):
        raise ValueError(
            "Jira answered with %s where a page of issues was expected"
            % type(page).__name__
        )
    issues = page.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError(
            "Jira's page has %s in it where the issues should be"
            % type(issues).__name__
        )
    return issues


def _record(issue: Any) -> dict:
    """One issue as a flat record: its fields lifted up beside its key.

    A field that collides with `id` or `key` is refused rather than resolved.
    Jira names fields by id -- summary, status, customfield_10010 -- so this is
    not something a real site does, and picking a winner quietly would drop
    either the issue's identity or the field that was asked for.
    """
    if not isinstance(issue, dict):
        raise ValueError(
            "Jira returned %s where an issue was expected" % type(issue).__name__
        )
    record = {key: issue[key] for key in ISSUE_KEYS if key in issue}
    fields = issue.get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError(
            "issue %s has %s where its fields should be"
            % (issue.get("key", "?"), type(fields).__name__)
        )
    for name, value in fields.items():
        if name in record:
            raise ValueError(
                "issue %s has a field called %r, which is also what the issue's "
                "own %r is called; one would be written over the other"
                % (issue.get("key", "?"), name, name)
            )
        record[name] = value
    return record


def _jql(args: dict) -> str:
    """What to fetch, which nothing else can stand in for.

    An empty query is refused rather than sent: to Jira it means every issue on
    the site, which is not what somebody who left --jql blank was asking for.
    """
    jql = get_str(args, "jql").strip()
    if not jql:
        raise ValueError("--jql is empty; it has to say which issues to fetch")
    return jql


def _fields(args: dict) -> List[str]:
    """Which fields to ask for, as the list Jira wants."""
    named = [part.strip() for part in get_str(args, "fields", DEFAULT_FIELDS).split(",")]
    fields = [part for part in named if part]
    if not fields:
        raise ValueError("--fields names no fields; leave it out to ask for the usual")
    return fields


def _limit(args: dict) -> Optional[int]:
    """How many records to stop at, or None to fetch the lot."""
    if "max_records" not in args:
        return None
    limit = get_int(args, "max_records")
    if limit < 1:
        raise ValueError("--max-records must be at least 1, got %d" % limit)
    return limit


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
    given with nothing in it is that mistake rather than the other: falling back
    to the environment there would answer a question nobody asked.
    """
    if name in args:
        given = get_str(args, name).strip()
        if not given:
            raise ValueError("--%s was given with nothing in it" % name)
        return given
    value = os.environ.get(env, "").strip()
    if not value:
        raise ValueError(
            "--%s was not given and %s is not set; jira needs both the site and "
            "the account to ask it as" % (name, env)
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


def _post_page(site: Dict[str, str], body: dict) -> dict:
    """Send one search and decode what comes back."""
    request = urllib.request.Request(
        site["url"] + SEARCH_PATH,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Basic %s" % _credentials(site),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # Before URLError, which it inherits from: a refusal Jira explained is
        # worth reading, and a bad JQL is only ever explained this way.
        raise ValueError("Jira refused the request: %s" % _refusal(exc))
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
    """The status, and whatever Jira said about it.

    Jira puts the useful half of a refusal in the body -- which JQL clause it
    could not parse, which field does not exist -- and that is the half worth
    printing. A wrong email or token says only 401, so that one gets a hint.
    """
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
