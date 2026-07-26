"""Locating script files by name.

Resolution order is fixed and never configurable:

    1. the current working directory
    2. every directory listed in the PGM_PATHS environment variable
    3. the scripts/ directory shipped inside the pgm package

The first match wins, which is what makes a local file able to shadow a
packaged one without any registration step.

Each of those may have folders inside it, and pgm looks through them: folders
are for organising, so `pgm randint` finds gen/randint.py without being told
where it went, and moving a script does not break what calls it. A script can
also be named by its folder -- `pgm gen/randint` -- which is how you say which
one you meant when two folders under one search directory used the same name.
"""

import os
from pathlib import Path
from typing import List, Optional

from .errors import PgmError, ScriptNotFoundError
from .runner import describe

PGM_PATHS_ENV = "PGM_PATHS"
SCRIPT_SUFFIX = ".py"

#: How many folders deep pgm looks below a search directory. Deep enough to
#: organise with, shallow enough that the working directory being a search
#: path does not turn every run into a walk of the whole tree.
MAX_DEPTH = 3


def bundled_scripts_dir() -> Path:
    """The scripts/ directory that ships with the pgm package."""
    return Path(__file__).resolve().parent / "scripts"


def env_paths() -> List[Path]:
    """Directories from PGM_PATHS, in the order the user listed them."""
    raw = os.environ.get(PGM_PATHS_ENV, "")
    paths = []
    for entry in raw.split(os.pathsep):
        entry = entry.strip()
        if entry:
            paths.append(Path(entry).expanduser())
    return paths


def search_paths() -> List[Path]:
    """Every directory pgm will look in, in resolution order."""
    return [Path.cwd()] + env_paths() + [bundled_scripts_dir()]


def script_filename(name: str) -> str:
    """Normalize a script name into the file name it must live in.

    A name may name a folder below a search directory -- generators/randint --
    but never a way out of one: a script is something pgm can find, not any
    file on the machine.
    """
    given = name.strip()
    if not given:
        raise PgmError("script name must not be empty")
    parts = given.replace(os.sep, "/")
    if os.altsep:
        parts = parts.replace(os.altsep, "/")
    if parts.endswith(SCRIPT_SUFFIX):
        parts = parts[: -len(SCRIPT_SUFFIX)]
    pieces = parts.split("/")
    if any(piece in ("", ".", "..") for piece in pieces):
        raise PgmError(
            "script name %r must be a name, or a name inside a folder like "
            "'generators/randint'; to run a file anywhere else, add its "
            "directory to %s" % (given, PGM_PATHS_ENV)
        )
    return "/".join(pieces) + SCRIPT_SUFFIX


def scripts_in(directory: Path) -> List[Path]:
    """Every script a search directory offers.

    Folders inside a directory that was named as a place for scripts are
    organisation, and pgm looks through them. The working directory is read
    only at the top: it is wherever you happen to be standing, and walking it
    would turn every run into a search of somebody's whole project, full of
    files that were never meant to be scripts. A folder there can still be
    named outright -- `pgm generators/randint` -- it just is not searched for.
    """
    return _walk(directory, 0 if directory == Path.cwd() else MAX_DEPTH)


def _walk(directory: Path, remaining: int) -> List[Path]:
    """Script files here, and below if there is depth left to spend.

    Folders whose names start with a dot or an underscore are left alone, so
    __pycache__, .git and a virtualenv are never walked into.
    """
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return []
    found = [
        entry
        for entry in entries
        if entry.suffix == SCRIPT_SUFFIX
        and not entry.name.startswith("_")
        and entry.is_file()
    ]
    if remaining:
        for entry in entries:
            if not entry.name.startswith((".", "_")) and entry.is_dir():
                found.extend(_walk(entry, remaining - 1))
    return found


def qualified_name(path: Path, directory: Path) -> str:
    """What to call a script, counting from the search directory it is in."""
    try:
        relative = path.relative_to(directory)
    except ValueError:
        return path.stem
    return "/".join(relative.with_suffix("").parts)


def find_script(name: str) -> Path:
    """Return the path of the first script matching ``name``.

    A name that says its folder is looked for exactly there. A bare name is
    looked for at the top of each search directory first -- which is one stat
    and the usual answer -- and only then in the folders below it.

    Raises ScriptNotFoundError listing the directories that were searched.
    """
    filename = script_filename(name)
    searched = []
    for directory in search_paths():
        searched.append(directory)
        candidate = directory / filename
        if candidate.is_file():
            return candidate
        if "/" in filename:
            continue  # A name that says where it lives is not looked for elsewhere.
        matches = [p for p in scripts_in(directory) if p.name == filename]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ScriptNotFoundError(
                "%r is ambiguous in %s; it could be %s. Say which one."
                % (
                    name,
                    directory,
                    " or ".join(qualified_name(p, directory) for p in matches),
                )
            )
    listing = "\n".join("  %s" % d for d in searched)
    raise ScriptNotFoundError(
        "no script named %r found; searched:\n%s" % (name, listing)
    )


def resolve(name: str) -> Optional[Path]:
    """Like find_script but returns None instead of raising."""
    try:
        return find_script(name)
    except ScriptNotFoundError:
        return None


def list_scripts() -> List[dict]:
    """Every reachable script, with the shadowed duplicates marked.

    Returns dicts of {name, qualname, path, source, active, entry, summary}
    ordered by search path so the output doubles as an explanation of the
    resolution order. `name` is what you type, `qualname` says which folder it
    came from, and the last two come from reading each file, never running it.

    `active` means this is the file the name actually resolves to, so a script
    made unreachable by an earlier one -- or by a namesake in a folder beside
    it -- is marked either way.
    """
    bundled = bundled_scripts_dir()
    cwd = Path.cwd()
    found = []
    seen = set()
    for directory in search_paths():
        if directory == cwd:
            source = "local"
        elif directory == bundled:
            source = "package"
        else:
            source = PGM_PATHS_ENV
        entries = scripts_in(directory)
        here = [entry.name for entry in entries]
        for entry in sorted(entries, key=lambda e: qualified_name(e, directory)):
            name = entry.stem
            found.append(
                dict(
                    describe(entry),
                    name=name,
                    qualname=qualified_name(entry, directory),
                    path=str(entry),
                    source=source,
                    active=name not in seen and here.count(entry.name) == 1,
                )
            )
            seen.add(name)
    return found
