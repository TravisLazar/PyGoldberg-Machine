"""Locating script files by name.

Resolution order is fixed and never configurable:

    1. the current working directory
    2. every directory listed in the PGM_PATHS environment variable
    3. the scripts/ directory shipped inside the pgm package

The first match wins, which is what makes a local file able to shadow a
packaged one without any registration step.
"""

import os
from pathlib import Path
from typing import List, Optional

from .errors import PgmError, ScriptNotFoundError

PGM_PATHS_ENV = "PGM_PATHS"
SCRIPT_SUFFIX = ".py"


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
    """Normalize a script name into the file name it must live in."""
    name = name.strip()
    if not name:
        raise PgmError("script name must not be empty")
    if os.sep in name or (os.altsep and os.altsep in name):
        raise PgmError(
            "script name %r must be a bare name, not a path; add its directory "
            "to %s instead" % (name, PGM_PATHS_ENV)
        )
    if name.endswith(SCRIPT_SUFFIX):
        name = name[: -len(SCRIPT_SUFFIX)]
    if not name:
        raise PgmError("script name must not be empty")
    return name + SCRIPT_SUFFIX


def find_script(name: str) -> Path:
    """Return the path of the first script matching ``name``.

    Raises ScriptNotFoundError listing the directories that were searched.
    """
    filename = script_filename(name)
    searched = []
    for directory in search_paths():
        searched.append(directory)
        candidate = directory / filename
        if candidate.is_file():
            return candidate
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

    Returns dicts of {name, path, source, active} ordered by search path so the
    output doubles as an explanation of the resolution order.
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
        try:
            entries = sorted(directory.glob("*" + SCRIPT_SUFFIX))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_file() or entry.name.startswith("_"):
                continue
            name = entry.stem
            found.append(
                {
                    "name": name,
                    "path": str(entry),
                    "source": source,
                    "active": name not in seen,
                }
            )
            seen.add(name)
    return found
