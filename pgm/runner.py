"""Loading a script file and calling its run() function."""

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import List

from .errors import InvalidScriptError, PgmError
from .streams import render

RUN_FUNCTION = "run"


class ScriptFailedError(PgmError):
    """run() raised. Keeps the original exception for the CLI to report."""

    def __init__(self, path: Path, record: dict, cause: BaseException):
        super().__init__("%s raised %s: %s" % (path.name, type(cause).__name__, cause))
        self.path = path
        self.record = record
        self.cause = cause


def load_module(path: Path) -> ModuleType:
    """Import a script file as a throwaway module.

    The module is registered under a pgm-private name so that dataclasses,
    pickling and anything else that looks itself up in sys.modules works.
    """
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
    return module


def get_run(module: ModuleType, path: Path):
    """Fetch and validate the script's run() entry point."""
    func = getattr(module, RUN_FUNCTION, None)
    if func is None:
        raise InvalidScriptError(
            "%s defines no %s() function; every pgm script must define "
            "run(args: dict, data: dict)" % (path, RUN_FUNCTION)
        )
    if not callable(func):
        raise InvalidScriptError("%s defines %s but it is not callable" % (path, RUN_FUNCTION))
    try:
        signature = inspect.signature(func)
        signature.bind({}, {})
    except TypeError:
        raise InvalidScriptError(
            "%s: %s%s cannot be called as %s(args: dict, data: dict)"
            % (path, RUN_FUNCTION, signature, RUN_FUNCTION)
        )
    except ValueError:
        pass  # Builtins and C callables have no introspectable signature.
    return func


def run_script(path: Path, args: dict, records: List[dict]) -> List[str]:
    """Call run() once per input record and collect the rendered output.

    Every record sees the same options, as its own copy: one call cannot reach
    the next one by writing into the args dict.
    """
    func = get_run(load_module(path), path)
    lines = []
    for record in records:
        try:
            result = func(dict(args), record)
        except PgmError:
            raise
        except Exception as exc:
            raise ScriptFailedError(path, record, exc)
        lines.extend(render(result))
    return lines
