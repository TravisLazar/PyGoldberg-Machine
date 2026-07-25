# PyGoldberg-Machine

An opinionated framework for running modular building blocks of functionality,
each one a single Python file. `pgm` finds a script by name, feeds it data, and
prints what it returns — so scripts chain together with a plain shell pipe.

```console
$ pgm hello
{"greeting": "Hello, Anonymous!", "name": "Anonymous"}

$ pgm --name=Travis --shout hello
{"greeting": "HELLO, TRAVIS!", "name": "Travis"}

$ pgm --count=3 --end=9 randint
{"value": 0}
{"value": 8}
{"value": 7}
```

## Install

```console
$ poetry install      # development
$ pip install .       # or install the built wheel
```

Both give you the `pgm` command.

## Writing a script

A script is one Python file defining `run`:

```python
def run(args: dict, data: dict) -> dict:
    factor = args.get("factor", 2)
    return {"scaled": data["number"] * factor}
```

That is the whole contract. `args` is what the command line asked for, `data` is
one record of input. A script never reads stdin, never prints, and never parses
arguments — pgm owns both ends. It returns a dict, a list of dicts, or the path
of a file it wrote.

## Finding scripts

`pgm do_something` looks for `do_something.py` in this order, first match wins:

1. the current working directory
2. every directory in the `PGM_PATHS` environment variable (`:`-separated,
   searched left to right)
3. the `scripts/` directory shipped inside the `pgm` package

So a file in the directory you are standing in transparently shadows a packaged
one. `pgm --list` shows everything reachable, with shadowed entries marked `#`;
`pgm --where <name>` prints the file a name resolves to; `pgm --paths` prints
the search order.

## Arguments

`--list`, `--where`, `--paths`, `--traceback`, `--version` and `--help` are
pgm's, that list is closed, and those names are reserved — giving one a value
(`--traceback=true`) is an error rather than an option that quietly turns into
the script's. **Every other option on the line is parsed and handed to the
script as `args`**, whether it comes before the script name or after it:

```console
$ pgm --dry hello                  # {"dry": true}
$ pgm --verbosity=3 hello          # {"verbosity": 3}
$ pgm --logpath=path/to/file hello # {"logpath": "path/to/file"}
$ pgm hello --dry --verbosity=3    # {"dry": true, "verbosity": 3}
```

**A value is always attached with `=`.** There is no `--name value` form, and
that one restriction is what keeps the rest simple:

| on the command line | in `args` |
| --- | --- |
| `--name=value` | `value` |
| `--name` | `true` |
| `--log-path=x` | key `log_path` — dashes become underscores |
| `--offset=-3` | `-3` |

Because every option carries its own value, no token's meaning depends on what
sits next to it. Options can go before the script name, after it, or on both
sides, and the one bare word on the line is always the script to run. Writing a
value with a space is a clear error rather than a misparse:

```console
$ pgm --logpath out.txt hello
pgm: more than one script name on the line ('out.txt', 'hello'); a value
     needs an '=' -- did you mean --logpath=out.txt?
```

A value that is **valid JSON arrives as JSON**, and anything else arrives as a
string — so `--verbosity=3` is the number `3`, `--dry=false` is `false`, and
`--logpath=out.txt` is a string, with no per-script wiring. That is also how you
pass a list: `--tags='["a", "b"]'`. Repeating an option is an error rather than a
silent last-one-wins, and so is a second bare word.

Each record gets its own copy of `args`, so a script that writes into the dict
cannot affect the next call.

## Input

pgm reads stdin and turns it into records, then calls `run` **once per record**.

| stdin | `run` receives |
| --- | --- |
| nothing | `{}`, once |
| `{"a": 1}` | `{"a": 1}` |
| one JSON object per line | each object, in turn |
| `[{"a": 1}, {"a": 2}]` | each element, in turn |
| a path to an existing file | the file's contents, parsed by these same rules |
| anything else | an error |

That last row is the whole point. There is no guessing and no wrapping: a line
that is not a JSON object, an array of them, or a path to a readable file is
input pgm refuses rather than input pgm invents a shape for. Bare scalars
(`41`, `true`, `"hello"`), loose text, and directories are all errors.

The path rule is what makes big payloads cheap: a script can hand the next
stage a filename instead of the data, and the next stage cannot tell the
difference. A path may be bare or a quoted JSON string, may appear inside an
array alongside objects, and may chain (a file containing a path to a file);
pgm stops with an error if the chain loops.

## Output

Whatever `run` returns is rendered to stdout, under the same narrow contract:

| return type | printed as |
| --- | --- |
| `dict` | one JSON object on one line |
| `list` | one element per line — each element a JSON object, or a quoted path that exists |
| `str` | printed directly — one line, and it must be a path to a file that exists |
| anything else | an error |

Only two things ever travel a pgm pipe: a JSON object and a reference to a file
holding JSON objects. So every return value must be exactly JSON or exactly a
path, and every other return is a bug pgm reports instead of printing. `None`,
`42`, a `set`, a `tuple`, a `Path` object, a `NaN` buried in a dict, a string
that names nothing on disk — all errors. Scripts that exist only for their side
effects return the file they wrote, or `{}`.

Because a `list` prints one record per line and stdin reads one record per
line, `pgm a | pgm b` fans out naturally: three records out of `a` means three
calls into `b`.

The bundled `randint` script returns a list, so it is a ready-made source. Given
a `double.py` next to you:

```python
def run(args: dict, data: dict) -> dict:
    return {"value": data["value"] * 2}
```

three records out of `randint` are three calls into `double`:

```console
$ pgm --count=3 --end=9 randint | pgm double
{"value": 0}
{"value": 16}
{"value": 14}
```

## Errors

Failures print one line on stderr and exit non-zero — a missing script, a file
with no `run`, a `run` that cannot take `(args, data)`, a command line pgm cannot
read, a raised exception, input pgm will not read, or a return value pgm will not
print. Pass `--traceback` to see the full stack when a script raises.

## Development

```console
$ poetry run pytest
```
