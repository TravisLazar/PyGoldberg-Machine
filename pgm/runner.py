"""Loading a script file and calling the function it runs on.

A script defines one of two entry points, and which one it defines is the
script's own business rather than something a caller has to remember:

    run(args: dict, data: dict)         one record at a time
    run_all(args: dict, records: list)  all of them at once

The second is for scripts that cannot answer until they have seen everything --
a histogram, a total, a sort. Both return the same things.
"""

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

from .errors import InvalidScriptError, PgmError
from .helpers import set_script_name
from .streams import render

RUN_FUNCTION = "run"
RUN_ALL_FUNCTION = "run_all"

#: How each entry point is meant to be called, for when one is not.
SIGNATURES = {
    RUN_FUNCTION: "run(args: dict, data: dict)",
    RUN_ALL_FUNCTION: "run_all(args: dict, records: list)",
}

#: Scripts already imported this process, so that calling one in a loop runs
#: its run() again and not its whole file.
_modules = {}  # type: Dict[Path, ModuleType]


class ScriptFailedError(PgmError):
    """The script raised. Keeps the original exception for the CLI to report."""

    def __init__(self, path: Path, data: Any, cause: BaseException):
        super().__init__("%s raised %s: %s" % (path.name, type(cause).__name__, cause))
        self.path = path
        #: What the call was given: one record, or all of them for run_all().
        self.data = data
        self.cause = cause


def load_module(path: Path) -> ModuleType:
    """Import a script file as a throwaway module.

    The module is registered under a pgm-private name so that dataclasses,
    pickling and anything else that looks itself up in sys.modules works, and
    kept, so that a script called many times is imported once like any import.
    """
    if path in _modules:
        return _modules[path]
    module_name = "pgm._scripts.%s" % path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise InvalidScriptError("%s is not an importable Python file" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except PgmError:
        raise
    except Exception as exc:
        del sys.modules[module_name]
        raise InvalidScriptError("%s failed to import: %s" % (path, exc))
    _modules[path] = module
    return module


def get_run(module: ModuleType, path: Path) -> Tuple[Any, bool]:
    """Fetch and validate the script's entry point.

    Returns the function and whether it wants every record at once.
    """
    one = getattr(module, RUN_FUNCTION, None)
    every = getattr(module, RUN_ALL_FUNCTION, None)
    if one is not None and every is not None:
        raise InvalidScriptError(
            "%s defines both %s() and %s(); a script takes one record at a "
            "time or all of them, not both" % (path, RUN_FUNCTION, RUN_ALL_FUNCTION)
        )
    if every is not None:
        return _checked(every, path, RUN_ALL_FUNCTION), True
    if one is None:
        raise InvalidScriptError(
            "%s defines no %s() function; every pgm script must define %s or %s"
            % (path, RUN_FUNCTION, SIGNATURES[RUN_FUNCTION], SIGNATURES[RUN_ALL_FUNCTION])
        )
    return _checked(one, path, RUN_FUNCTION), False


def _checked(func: Any, path: Path, name: str) -> Any:
    """Make sure the entry point can be called the way pgm calls it."""
    if not callable(func):
        raise InvalidScriptError("%s defines %s but it is not callable" % (path, name))
    try:
        signature = inspect.signature(func)
        signature.bind({}, {})
    except TypeError:
        raise InvalidScriptError(
            "%s: %s%s cannot be called as %s" % (path, name, signature, SIGNATURES[name])
        )
    except ValueError:
        pass  # Builtins and C callables have no introspectable signature.
    return func


def run_script(path: Path, args: dict, records: Optional[List[dict]]) -> List[str]:
    """Call the script's entry point and collect the rendered output.

    `records` is None when nothing was piped in at all, which is not the same
    as an empty list: zero records is an answer, and a script that was given
    one runs zero times.

    So a run() script is called once per record, and nothing at all still gets
    one empty record, so that a script needing no input runs exactly once. A
    run_all() script is called once with the lot, and nothing stays nothing:
    there is no histogram of one blank row.

    Either way the call gets its own copy of the options, so one call cannot
    reach the next by writing into the args dict.
    """
    func, takes_all = get_run(load_module(path), path)
    set_script_name(path.stem)
    if takes_all:
        return _invoke(func, path, args, list(records or []))
    lines = []
    for record in [{}] if records is None else records:
        lines.extend(_invoke(func, path, args, record))
    return lines


def _invoke(func: Any, path: Path, args: dict, data: Any) -> List[str]:
    """Call the entry point once, and render whatever it hands back."""
    try:
        result = func(dict(args), data)
    except PgmError:
        raise
    except Exception as exc:
        raise ScriptFailedError(path, data, exc)
    return render(result)
