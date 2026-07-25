"""The pgm command line entry point."""

import argparse
import sys
import traceback

from . import __version__
from .args import parse_script_args, split_argv
from .discovery import PGM_PATHS_ENV, find_script, list_scripts, search_paths
from .errors import PgmError
from .runner import ScriptFailedError, run_script
from .streams import read_records, read_stdin, write_lines

USAGE = "pgm [pgm options] <script> [script options]"

DESCRIPTION = """\
Run a pgm script by name.

Scripts are plain Python files exposing run(args: dict, data: dict). pgm reads
stdin, calls run() once per input record, and prints whatever run() returns.

The options below are pgm's own. Every other option on the line is parsed and
handed to the script as args: --dry becomes {"dry": true}, --verbosity=3
becomes {"verbosity": 3}, and --logpath=out.txt becomes {"logpath": "out.txt"}.
A value is always attached with '=', so options may sit anywhere on the line.
"""

EPILOG = """\
resolution order:
  1. the current directory
  2. the directories in %s
  3. the scripts shipped with pgm
""" % PGM_PATHS_ENV


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pgm",
        usage=USAGE,
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("script", nargs="?", help="name of the script to run")
    parser.add_argument(
        "--list", action="store_true", help="list every script pgm can see"
    )
    parser.add_argument(
        "--where",
        action="store_true",
        help="print the file a script name resolves to instead of running it",
    )
    parser.add_argument(
        "--paths", action="store_true", help="print the search path, in order"
    )
    parser.add_argument(
        "--traceback",
        action="store_true",
        help="show the full traceback when a script raises",
    )
    parser.add_argument("--version", action="version", version="pgm %s" % __version__)
    return parser


def _print_paths(out) -> int:
    for directory in search_paths():
        out.write("%s\n" % directory)
    return 0


def _print_listing(out) -> int:
    scripts = list_scripts()
    if not scripts:
        return 0
    width = max(len(s["name"]) for s in scripts)
    for script in scripts:
        marker = " " if script["active"] else "#"
        out.write(
            "%s %-*s  %-8s %s\n"
            % (marker, width, script["name"], script["source"], script["path"])
        )
    return 0


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    # Read straight off the line: splitting it can fail, and a failure there
    # still deserves a traceback if one was asked for.
    show_traceback = "--traceback" in argv

    try:
        # argparse only ever sees pgm's own options; the script's are not ours
        # to validate, and handing them over would have argparse reject them.
        pgm_options, script, extra = split_argv(list(argv))
        args = parser.parse_args(pgm_options + ([script] if script else []))

        if args.paths:
            return _print_paths(sys.stdout)
        if args.list:
            return _print_listing(sys.stdout)
        if not args.script:
            parser.print_help(sys.stderr)
            return 2

        path = find_script(args.script)
        if args.where:
            sys.stdout.write("%s\n" % path)
            return 0

        script_args = parse_script_args(extra)
        # Nothing on stdin is None rather than []: it means no input was given,
        # not that the input was a list of no records.
        records = read_records(read_stdin(sys.stdin)) or None
        write_lines(run_script(path, script_args, records), sys.stdout)
        return 0
    except BrokenPipeError:
        # The downstream end of the pipe went away; that is not our failure.
        return 0
    except KeyboardInterrupt:
        return 130
    except ScriptFailedError as exc:
        if show_traceback:
            traceback.print_exception(
                type(exc.cause), exc.cause, exc.cause.__traceback__, file=sys.stderr
            )
        sys.stderr.write("pgm: %s\n" % exc)
        return 1
    except PgmError as exc:
        sys.stderr.write("pgm: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
